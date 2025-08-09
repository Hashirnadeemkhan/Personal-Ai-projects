Airline Customer Service Assistant
==================================

Overview
--------

The **Airline Customer Service Assistant** is a web-based application built using **Streamlit** and powered by an AI-driven agent system. It provides a conversational interface to assist airline customers with tasks such as checking flight status, updating seat assignments, answering frequently asked questions (FAQs), retrieving airport and airline information, and managing passenger details. The application integrates with external APIs (e.g., AviationStack) and uses MongoDB for persistent storage, with fallback to in-memory storage for resilience.

The system employs a multi-agent architecture, where specialized agents handle specific tasks (e.g., flight status, seat booking) and a triage agent routes requests to the appropriate agent. The application is designed to be professional, user-friendly, and scalable, with robust error handling and logging.

Features
--------

*   **Flight Status Checking**: Retrieve real-time or historical flight status using the AviationStack API.
    
*   **Seat Assignment Updates**: View available seats and update seat assignments with validation.
    
*   **FAQ Handling**: Answer common questions about airline policies (e.g., baggage, Wi-Fi).
    
*   **Airport Information**: Provide details about airports using IATA codes.
    
*   **Airline Information**: Retrieve airline details such as fleet size and founding date.
    
*   **Passenger Management**: Set and store passenger names for personalized interactions.
    
*   **Persistent Storage**: Store conversation history and context in MongoDB, with in-memory fallback.
    
*   **Multi-Agent System**: Specialized agents for task-specific handling, with a triage agent for request routing.
    
*   **Error Handling & Logging**: Comprehensive logging and user-friendly error messages.
    

Tech Stack
----------

*   **Frontend**: Streamlit
    
*   **Backend**: Python 3.8+
    
*   **AI Framework**: Custom agent system with OpenAI-compatible API (using Gemini API)
    
*   **Database**: MongoDB (with in-memory storage fallback)
    
*   **APIs**: AviationStack API for flight, airport, and airline data
    
*   **Libraries**:
    
    *   streamlit: Web interface
        
    *   pymongo: MongoDB integration
        
    *   requests: API calls
        
    *   pydantic: Data validation
        
    *   python-dotenv: Environment variable management
        
    *   logging: Application logging
        
*   **Environment**: Configured via .env file
    

Installation
------------

### Prerequisites

*   Python 3.8 or higher
    
*   MongoDB instance (optional, for persistent storage)
    
*   API keys for:
    
    *   Gemini API (GEMINI\_API\_KEY)
        
    *   AviationStack API (AVIATION\_API\_KEY)
        
    *   MongoDB connection string (MONGODB\_URI)
        

### Setup

1.  git clone https://github.com/your-repo/airline-customer-service.gitcd airline-customer-service
    
2.  pip install -r requirements.txt
    
3.  GEMINI\_API\_KEY=your\_gemini\_api\_key
    
4.  AVIATION\_API\_KEY=your\_aviationstack\_api\_key
    
5.  MONGODB\_URI=your\_mongodb\_connection\_string
    
6.  streamlit run app.py
    
7.  **Access the Application**:Open your browser to http://localhost:8501.
    

Usage
-----

1.  **Start the Application**: Launch the Streamlit app.
    
2.  **Interact via Chat Interface**:
    
    *   Enter queries like:
        
        *   "Check AA123 status"
            
        *   "Update seat for ABC123 to 12A"
            
        *   "What’s the baggage policy?"
            
        *   "Tell me about SFO"
            
        *   "My name is John Smith"
            
    *   The assistant responds in a conversational, professional manner.
        
3.  **Conversation History**: View all interactions in the chat interface, persisted across sessions via MongoDB or in-memory storage.
    
4.  **Error Handling**: The system provides clear error messages for invalid inputs (e.g., incorrect flight numbers or seat formats).
    

Project Structure
-----------------

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   airline-customer-service/  ├── app.py                  # Main Streamlit application  ├── agents.py               # Agent definitions and tools  ├── requirements.txt        # Python dependencies  ├── .env                    # Environment variables (not tracked)  ├── README.md               # Project documentation  └── in_memory_storage/      # (Optional) In-memory storage fallback   `

Dependencies
------------

Listed in requirements.txt:

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   streamlit  pymongo  requests  pydantic  python-dotenv   `

Error Handling
--------------

*   **MongoDB Connection**: Falls back to in-memory storage if MongoDB connection fails.
    
*   **API Failures**: Displays user-friendly error messages and logs details for debugging.
    
*   **Input Validation**: Validates inputs (e.g., IATA codes, confirmation numbers, seat formats) with clear feedback.
    

Logging
-------

*   Logs are configured to output to the console with timestamps and log levels (INFO, ERROR).
    
*   Key actions (e.g., API calls, context updates) are logged for traceability.
    

Future Enhancements
-------------------

*   Support for additional APIs (e.g., FlightAware, FlightRadar24).
    
*   Enhanced UI with advanced chat features (e.g., message editing, rich media).
    
*   Integration with additional AI models for improved responses.
    
*   Support for multi-language interactions.
    
*   Advanced analytics for conversation tracking.
    

Contributing
------------

Contributions are welcome! Please:

1.  Fork the repository.
    
2.  Create a feature branch (git checkout -b feature/your-feature).
    
3.  Commit changes (git commit -m "Add your feature").
    
4.  Push to the branch (git push origin feature/your-feature).
    
5.  Open a pull request.
    

License
-------

This project is licensed under the MIT License. See the LICENSE file for details.

Contact
-------

For issues or inquiries, please contact \[[your-email@example.com](mailto:your-email@example.com)\] or open an issue on GitHub.
