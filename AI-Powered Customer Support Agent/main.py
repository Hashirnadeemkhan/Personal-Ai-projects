import streamlit as st
import asyncio
import random
import uuid
import re
import requests
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from pymongo.collection import Collection
from datetime import datetime
import logging
from agents import (
    Agent,
    HandoffOutputItem,
    ItemHelpers,
    MessageOutputItem,
    RunContextWrapper,
    Runner,
    function_tool,
    handoff,
    trace,
    OpenAIChatCompletionsModel,
    AsyncOpenAI,
    set_tracing_disabled,
)
from dotenv import load_dotenv
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Validate environment variables
required_env_vars = ["GEMINI_API_KEY", "AVIATION_API_KEY", "MONGODB_URI"]
for var in required_env_vars:
    if not os.getenv(var):
        st.error(f"Missing environment variable: {var}")
        st.stop()

# Initialize MongoDB client
mongo_client: Optional[MongoClient] = None
db: Optional[Any] = None
conversations_collection: Optional[Collection] = None
use_mongodb: bool = True
in_memory_storage: Dict[str, Any] = {}

try:
    mongo_client = MongoClient(
        os.getenv("MONGODB_URI"),
        server_api=ServerApi('1'),
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=20000,
        socketTimeoutMS=20000,
        tls=True,
        tlsAllowInvalidCertificates=False
    )
    if mongo_client is not None:
        mongo_client.admin.command('ping')
        st.success("Connected to MongoDB!")
        db = mongo_client["airline_customer_service"]
        conversations_collection = db["conversations"]
except Exception as e:
    st.error(f"Failed to connect to MongoDB: {str(e)}. Using in-memory storage.")
    use_mongodb = False

# Initialize provider and model
try:
    provider = AsyncOpenAI(
        api_key=os.getenv("GEMINI_API_KEY"),
        base_url="https://generativelanguage.googleapis.com/v1beta",
    )
    model = OpenAIChatCompletionsModel(model="gemini-2.5-flash", openai_client=provider)
except Exception as e:
    st.warning(f"Failed to initialize Gemini API: {str(e)}. Using mock responses for testing.")

# Airline Agent Context
class AirlineAgentContext(BaseModel):
    passenger_name: Optional[str] = None
    confirmation_number: Optional[str] = None
    flight_number: Optional[str] = None
    seat_number: Optional[str] = None
    flight_status: Optional[Dict[str, Any]] = None
    airport_info: Optional[Dict[str, Any]] = None
    airline_info: Optional[Dict[str, Any]] = None

# AviationStack API Helper
async def fetch_aviation_data(endpoint: str, params: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    base_url = "https://api.aviationstack.com/v1/"
    params["access_key"] = os.getenv("AVIATION_API_KEY")
    try:
        response = requests.get(f"{base_url}{endpoint}", params=params, timeout=10)
        response.raise_for_status()
        return response.json().get("data", [])
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch data from {endpoint}: {str(e)}")
        return None

# Tools
@function_tool(description_override="Lookup frequently asked questions about the airline.")
async def faq_lookup_tool(question: str) -> str:
    question_lower = question.lower().strip()
    faqs = {
        "wifi": "Most flights offer free Wi-Fi. Connect to the 'Airline-Wifi' network during your flight.",
        "baggage": "Passengers are allowed one carry-on bag (up to 22 x 14 x 9 inches) and one checked bag (up to 62 linear inches) free of charge. Additional bags may incur fees.",
        "seats": "Our aircraft typically have 120-180 seats, including economy, premium economy, and business class options.",
        "check-in": "Online check-in is available 24 hours before departure via our website or mobile app."
    }
    for key, answer in faqs.items():
        if key in question_lower:
            return answer
    return "Sorry, I don't have information on that topic. Can I assist with something else?"

@function_tool(description_override="Set the passenger's name in the context.")
async def set_passenger_name(context: RunContextWrapper[AirlineAgentContext], name: str) -> str:
    if not name or not re.match(r"^[A-Za-z\s]{1,50}$", name):
        return "Please provide a valid name (letters and spaces only, up to 50 characters). Example: John Smith"
    
    context.context.passenger_name = name.strip().title()
    await update_context_in_storage(context)
    return f"Your name has been set to {context.context.passenger_name}. How can I assist you further?"

@function_tool(description_override="Retrieve available seats for a flight.")
async def get_seat_map(context: RunContextWrapper[AirlineAgentContext], flight_number: str) -> str:
    if not flight_number or not re.match(r"^[A-Za-z]{2}[0-9]{1,4}$", flight_number):
        return "Please provide a valid IATA flight number (e.g., AA123)."

    flight_data = await fetch_aviation_data("flights", {"flight_iata": flight_number})
    if not flight_data:
        return f"No flight data found for {flight_number}. Please check the flight number (e.g., AA123)."

    aircraft_iata = flight_data[0].get("aircraft", {}).get("iata", "A320")
    seat_configs = {
        "A320": ["1A", "1B", "1C", "1D", "2A", "2B", "2C", "2D", "10A", "10F", "15A", "15F"],
        "B737": ["5A", "5B", "5C", "5D", "6A", "6B", "6C", "6D", "20A", "20F"],
        "A321": ["12A", "12B", "12C", "12D", "15A", "15F", "25A", "25F"]
    }
    available_seats = seat_configs.get(aircraft_iata, ["12A", "12B", "15C", "15D"])
    return f"Available seats for flight {flight_number} ({aircraft_iata}): {', '.join(available_seats)}"

@function_tool(description_override="Update a passenger's seat assignment.")
async def update_seat(context: RunContextWrapper[AirlineAgentContext], confirmation_number: str, new_seat: str) -> str:
    if not confirmation_number or not re.match(r"^[A-Za-z0-9]{2,10}$", confirmation_number):
        return "Please provide a valid confirmation number (2-10 alphanumeric characters). Example: ABC123"
    if not new_seat or not re.match(r"^[0-9]{1,3}[A-Fa-f]$", new_seat, re.IGNORECASE):
        return f"Please provide a valid seat number (e.g., 12A). Use the seat map tool to see available seats."

    flight_number = context.context.flight_number or "AA123"
    seat_map = await get_seat_map(context, flight_number)
    available_seats = [seat.strip() for seat in seat_map.split(": ")[-1].split(", ")]
    if new_seat.upper() not in available_seats:
        return f"Seat {new_seat} is not available. Available seats: {', '.join(available_seats)}"

    context.context.seat_number = new_seat.upper()
    context.context.confirmation_number = confirmation_number
    if not context.context.flight_number:
        context.context.flight_number = flight_number

    await update_context_in_storage(context)
    return f"Your seat has been updated to {new_seat.upper()} for confirmation number {confirmation_number} on flight {context.context.flight_number}."

@function_tool(description_override="Retrieve real-time or historical flight status.")
async def get_flight_status(context: RunContextWrapper[AirlineAgentContext], flight_number: str) -> str:
    if not re.match(r"^[A-Za-z]{2}[0-9]{1,4}$", flight_number):
        return "Please provide a valid IATA flight number (e.g., AA123 or UA456)."

    flight_data = await fetch_aviation_data("flights", {"flight_iata": flight_number})
    if not flight_data:
        return f"No information found for flight {flight_number}. Please check the flight number (e.g., AA123) or try sites like FlightAware (flightaware.com)."

    flight = flight_data[0]
    status = {
        "flight_number": flight.get("flight", {}).get("iata", flight_number),
        "status": flight.get("flight_status", "Unknown"),
        "departure": flight.get("departure", {}).get("airport", "Unknown"),
        "arrival": flight.get("arrival", {}).get("airport", "Unknown"),
        "scheduled_departure": flight.get("departure", {}).get("scheduled", "Unknown"),
        "delay": flight.get("departure", {}).get("delay", 0)
    }
    context.context.flight_status = status
    await update_context_in_storage(context)
    return (f"Flight {flight_number}: Status - {status['status']}, "
            f"Departure - {status['departure']}, Arrival - {status['arrival']}, "
            f"Scheduled - {status['scheduled_departure']}, Delay - {status['delay']} minutes")

@function_tool(description_override="Retrieve airport information by IATA code.")
async def get_airport_info(iata_code: str) -> str:
    if not re.match(r"^[A-Za-z]{3}$", iata_code):
        return "Please provide a valid IATA airport code (e.g., SFO)."

    airport_data = await fetch_aviation_data("airports", {"iata_code": iata_code})
    if not airport_data:
        return f"No information found for airport {iata_code}. Please check the code (e.g., SFO)."

    airport = airport_data[0]
    return (f"Airport {iata_code}: {airport.get('airport_name', 'Unknown')}, "
            f"Location: {airport.get('city_iata_code', 'Unknown')} ({airport.get('country_name', 'Unknown')}), "
            f"Timezone: {airport.get('timezone', 'Unknown')}")

@function_tool(description_override="Retrieve airline information by IATA code.")
async def get_airline_info(iata_code: str) -> str:
    if not re.match(r"^[A-Za-z0-9]{2}$", iata_code):
        return "Please provide a valid IATA airline code (e.g., AA)."

    airline_data = await fetch_aviation_data("airlines", {"iata_code": iata_code})
    if not airline_data:
        return f"No information found for airline {iata_code}. Please check the code (e.g., AA)."

    airline = airline_data[0]
    return (f"Airline {iata_code}: {airline.get('airline_name', 'Unknown')}, "
            f"Country: {airline.get('country_name', 'Unknown')}, "
            f"Fleet Size: {airline.get('fleet_size', 'Unknown')}, Founded: {airline.get('date_founded', 'Unknown')}")

async def update_context_in_storage(context: RunContextWrapper[AirlineAgentContext]) -> None:
    if use_mongodb and conversations_collection is not None:
        conversations_collection.update_one(
            {"conversation_id": st.session_state.conversation_id},
            {
                "$set": {
                    "context": context.context.dict(),
                    "messages": st.session_state.messages,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
    else:
        in_memory_storage[st.session_state.conversation_id] = {
            "context": context.context.dict(),
            "messages": st.session_state.messages,
            "updated_at": datetime.utcnow()
        }

async def on_seat_booking_handoff(context: RunContextWrapper[AirlineAgentContext]) -> None:
    if not context.context.flight_number:
        context.context.flight_number = f"FLT-{random.randint(100,999)}"
    await update_context_in_storage(context)

faq_agent = Agent[AirlineAgentContext](
    name="FAQ Agent",
    handoff_description="Answers common questions about the airline.",
    instructions="""
    You are an FAQ Agent for an airline, assisting with common questions in a polite, professional, and customer-friendly tone. Use the `faq_lookup_tool` to answer questions accurately. Follow this routine:
    1. Greet the customer, using their name if available (e.g., "Hello, [passenger_name]! How can I assist you?").
    2. Identify the last question and use `faq_lookup_tool` to answer it clearly.
    3. If the tool fails or returns no answer, apologize and transfer to the triage agent (e.g., "I'm sorry, I couldn't find that information. Let me connect you with our triage agent.").
    4. Confirm if the question was answered (e.g., "Does that help, or is there anything else?").
    5. Close politely if no further questions (e.g., "Thank you for reaching out! Have a great day.").
    Guidelines:
    - Always use `faq_lookup_tool`.
    - Use context (e.g., flight_number) when relevant.
    - Log interactions for traceability.
    - Transfer unrelated queries to the triage agent.
    """,
    tools=[faq_lookup_tool],
    model=model
)

seat_booking_agent = Agent[AirlineAgentContext](
    name="Seat Booking Agent",
    handoff_description="Helps customers update their seat assignments.",
    instructions="""
    You are a Seat Booking Agent, assisting with seat assignments in a polite, professional tone. Use `update_seat` and `get_seat_map` tools. Follow this routine:
    1. Greet the customer, using their name if available (e.g., "Hello, [passenger_name]! Let's update your seat.").
    2. Confirm or request the confirmation number (e.g., "Please provide your confirmation number, like ABC123.").
    3. Use `get_seat_map` to show available seats if needed (e.g., "Here are available seats: [seat_list].").
    4. Validate inputs (confirmation number, seat number) and use `update_seat` to update the assignment.
    5. Confirm the update (e.g., "Your seat is now [seat_number] for confirmation [confirmation_number].").
    6. Close politely (e.g., "Enjoy your flight! Anything else I can help with?").
    Guidelines:
    - Validate inputs and provide examples (e.g., "Confirmation like ABC123, seat like 12A").
    - Transfer unrelated queries to the triage agent.
    - Log interactions for traceability.
    """,
    tools=[update_seat, get_seat_map],
    model=model
)

flight_status_agent = Agent[AirlineAgentContext](
    name="Flight Status Agent",
    handoff_description="Retrieves real-time flight status.",
    instructions="""
    You are a Flight Status Agent, retrieving flight status in a polite, professional tone. Use `get_flight_status` tool. Follow this routine:
    1. Greet the customer, using their name if available (e.g., "Hello, [passenger_name]! Let me check your flight.").
    2. Confirm or request the flight number (e.g., "Please provide the flight number, like AA123.").
    3. Use `get_flight_status` to retrieve and share status (e.g., "Flight [flight_number] is [status]...").
    4. Confirm if the question was answered (e.g., "Does that cover it, or is there more I can help with?").
    5. Close politely (e.g., "Safe travels! Let me know if you need more help.").
    Guidelines:
    - Always use `get_flight_status`.
    - Validate flight numbers and provide examples (e.g., "AA123 or UA456").
    - Transfer invalid or unrelated queries to the triage agent.
    - Log interactions for traceability.
    """,
    tools=[get_flight_status],
    model=model
)

airport_info_agent = Agent[AirlineAgentContext](
    name="Airport Info Agent",
    handoff_description="Provides information about airports.",
    instructions="""
    You are an Airport Info Agent, providing airport details in a polite, professional tone. Use `get_airport_info` tool. Follow this routine:
    1. Greet the customer, using their name if available (e.g., "Hello, [passenger_name]! Let me get that airport info.").
    2. Request or confirm the airport IATA code (e.g., "Please provide the airport code, like SFO.").
    3. Use `get_airport_info` to retrieve and share details (e.g., "Airport [iata_code]: [airport_name]...").
    4. Confirm if the question was answered (e.g., "Is that what you needed, or can I help with more?").
    5. Close politely (e.g., "Thank you for reaching out! Safe travels.").
    Guidelines:
    - Always use `get_airport_info`.
    - Validate IATA codes and provide examples (e.g., "SFO or JFK").
    - Transfer unrelated queries to the triage agent.
    - Log interactions for traceability.
    """,
    model=model
)

airline_info_agent = Agent[AirlineAgentContext](
    name="Airline Info Agent",
    handoff_description="Provides information about airlines.",
    instructions="""
    You are an Airline Info Agent, providing airline details in a polite, professional tone. Use `get_airline_info` tool. Follow this routine:
    1. Greet the customer, using their name if available (e.g., "Hello, [passenger_name]! Let me get that airline info.").
    2. Request or confirm the airline IATA code (e.g., "Please provide the airline code, like AA.").
    3. Use `get_airline_info` to retrieve and share details (e.g., "Airline [iata_code]: [airline_name]...").
    4. Confirm if the question was answered (e.g., "Is that what you needed, or can I help with more?").
    5. Close politely (e.g., "Thank you for reaching out! Let me know if you need more help.").
    Guidelines:
    - Always use `get_airline_info`.
    - Validate IATA codes and provide examples (e.g., "AA or UA").
    - Transfer unrelated queries to the triage agent.
    - Log interactions for traceability.
    """,
    tools=[get_airline_info],
    model=model
)

triage_agent = Agent[AirlineAgentContext](
    name="Triage Agent",
    handoff_description="Delegates customer requests to the appropriate agent.",
    instructions="""
    You are a Triage Agent for an airline, delegating requests in a polite, professional tone. Follow this routine:
    1. Greet the customer, using their name if available (e.g., "Hello, [passenger_name]! How can I assist you today?").
    2. Analyze the request and delegate:
       - "name" or "passenger name": Use `set_passenger_name` (e.g., extract "John Smith" from "My name is John Smith").
       - General airline info (e.g., baggage, Wi-Fi): Transfer to FAQ Agent.
       - Seat updates: Transfer to Seat Booking Agent (trigger `on_seat_booking_handoff`).
       - Flight status: Transfer to Flight Status Agent.
       - Airport info (e.g., "about SFO"): Transfer to Airport Info Agent.
       - Airline info (e.g., "about American Airlines"): Transfer to Airline Info Agent.
       - Flight search: Respond, "I can't search flights, but try FlightAware (flightaware.com) or FlightRadar24 (flightradar24.com) for active flight numbers."
    3. If unclear, ask for clarification with examples (e.g., "Could you clarify? For example, say 'Check AA123 status' or 'Update seat to 12A'.").
    4. If no agent fits, apologize (e.g., "I'm sorry, I can't assist with that. Please try again or contact support.").
    Guidelines:
    - Use context (e.g., flight_number) to streamline handoffs.
    - Provide example inputs for unclear requests.
    - Log interactions for traceability.
    - Maintain a human-like, empathetic tone.
    """,
    tools=[set_passenger_name],
    handoffs=[
        faq_agent,
        handoff(agent=seat_booking_agent, on_handoff=on_seat_booking_handoff),
        flight_status_agent,
        airport_info_agent,
        airline_info_agent
    ],
    model=model
)

faq_agent.handoffs.append(triage_agent)
seat_booking_agent.handoffs.append(triage_agent)
flight_status_agent.handoffs.append(triage_agent)
airport_info_agent.handoffs.append(triage_agent)
airline_info_agent.handoffs.append(triage_agent)

set_tracing_disabled(disabled=True)

# Streamlit UI
st.set_page_config(page_title="Airline Customer Service", layout="wide")

# Initialize session state
if 'conversation_id' not in st.session_state:
    st.session_state.conversation_id = uuid.uuid4().hex[:16]
if 'input_items' not in st.session_state:
    st.session_state.input_items = []
if 'current_agent' not in st.session_state:
    st.session_state.current_agent = triage_agent
if 'context' not in st.session_state:
    st.session_state.context = AirlineAgentContext()
if 'messages' not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "Hello! I'm your Airline Customer Service Assistant. I can help with:\n"
                "- Checking flight status (e.g., 'Check AA123 status')\n"
                "- Updating seat assignments (e.g., 'Update seat for ABC123 to 12A')\n"
                "- Answering FAQs (e.g., 'What’s the baggage policy?')\n"
                "- Airport info (e.g., 'Tell me about SFO')\n"
                "- Airline info (e.g., 'Tell me about American Airlines')\n"
                "- Setting your name (e.g., 'My name is John Smith')\n"
                "What would you like to do?"
            )
        }
    ]

# Load conversation from storage
if use_mongodb and conversations_collection is not None:
    conversation = conversations_collection.find_one({"conversation_id": st.session_state.conversation_id})
    if conversation:
        st.session_state.context = AirlineAgentContext(**conversation.get("context", {}))
        st.session_state.messages = conversation.get("messages", st.session_state.messages)
else:
    if st.session_state.conversation_id in in_memory_storage:
        stored = in_memory_storage[st.session_state.conversation_id]
        st.session_state.context = AirlineAgentContext(**stored.get("context", {}))
        st.session_state.messages = stored.get("messages", st.session_state.messages)

# Header
st.title("✈️ Airline Customer Service Assistant")
st.markdown("I'm here to assist with your travel needs. Ask about flights, seats, airports, airlines, or general questions!")

# Chat container
chat_container = st.container()

# Input form
with st.form(key='user_input_form', clear_on_submit=True):
    user_input = st.text_input("Enter your message:", placeholder="E.g., Check AA123 status, update seat for ABC123 to 12A, or tell me about SFO")
    submit_button = st.form_submit_button("Send")

# Display chat history
with chat_container:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

# Handle form submission
if submit_button and user_input:
    async def process_input():
        with st.spinner("Processing your request..."):
            st.session_state.messages.append({"role": "user", "content": user_input})
            st.session_state.input_items.append({"content": user_input, "role": "user"})

            with trace("Customer service", group_id=st.session_state.conversation_id):
                result = await Runner.run(
                    st.session_state.current_agent,
                    st.session_state.input_items,
                    context=st.session_state.context
                )

                for new_item in result.new_items:
                    if isinstance(new_item, MessageOutputItem):
                        message = ItemHelpers.text_message_output(new_item)
                        st.session_state.messages.append({"role": "assistant", "content": message})

                st.session_state.input_items = result.to_input_list()
                st.session_state.current_agent = result.last_agent

                await update_context_in_storage(RunContextWrapper(st.session_state.context, None))

            with chat_container:
                for msg in st.session_state.messages:
                    with st.chat_message(msg["role"]):
                        st.markdown(msg["content"])

    try:
        asyncio.run(process_input())
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        st.error(f"Oops, something went wrong: {str(e)}. Please try again later.")