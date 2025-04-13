import streamlit as st
import requests
import json
import datetime
import os
import atexit

# Define constants
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CHAT_SESSIONS_FILE = os.path.join(DATA_DIR, "chat_sessions.json")

# --- App Configuration ---
def initialize_session_state():
    """Initialize all required session state variables."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "chat_sessions" not in st.session_state:
        st.session_state.chat_sessions = {}
    
    if "current_chat_name" not in st.session_state:
        st.session_state.current_chat_name = None
    
    if "current_chat_id" not in st.session_state:
        st.session_state.current_chat_id = None
    
    # Load saved chat sessions from file
    load_chat_sessions_from_file()

# --- File Persistence Functions ---
def ensure_data_directory():
    """Ensure the data directory exists."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def serialize_chat_sessions():
    """Convert chat sessions to serializable format."""
    serialized = {}
    for chat_id, chat_data in st.session_state.chat_sessions.items():
        serialized[chat_id] = {
            "messages": chat_data["messages"],
            "name": chat_data["name"],
            "timestamp": chat_data["timestamp"].isoformat()  # Convert datetime to string
        }
    return serialized

def deserialize_chat_sessions(serialized):
    """Convert serialized chat sessions back to original format."""
    deserialized = {}
    for chat_id, chat_data in serialized.items():
        deserialized[chat_id] = {
            "messages": chat_data["messages"],
            "name": chat_data["name"],
            "timestamp": datetime.datetime.fromisoformat(chat_data["timestamp"])  # Convert string to datetime
        }
    return deserialized

def save_chat_sessions_to_file():
    """Save all chat sessions to a JSON file."""
    ensure_data_directory()
    try:
        serialized = serialize_chat_sessions()
        with open(CHAT_SESSIONS_FILE, 'w') as f:
            json.dump(serialized, f)
        return True
    except Exception as e:
        st.error(f"Error saving chat sessions: {e}")
        return False

def load_chat_sessions_from_file():
    """Load chat sessions from a JSON file."""
    try:
        if os.path.exists(CHAT_SESSIONS_FILE):
            with open(CHAT_SESSIONS_FILE, 'r') as f:
                serialized = json.load(f)
                st.session_state.chat_sessions = deserialize_chat_sessions(serialized)
            return True
        return False
    except Exception as e:
        st.error(f"Error loading chat sessions: {e}")
        return False

# Register function to save chat sessions when the application exits
atexit.register(save_chat_sessions_to_file)

# --- API Communication ---
def send_request(prompt_text, history=None):
    """Send a query to the MCP backend server."""
    try:
        payload = {"query": prompt_text, "history": history}
        response = requests.post("http://localhost:8001/mcp/query", json=payload)
        
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Server error: {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Request failed: {e}")
        st.error("Make sure LLM and MCP server are initialized")
        return None

def update_mcp_server(server_config):
    """Update MCP server configuration."""
    try:
        payload = {"mcp_server": server_config}
        response = requests.post("http://localhost:8001/mcp/update", json=payload)
        
        if response.status_code == 200:
            return True
        else:
            st.error(f"Error updating MCP server: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        st.error(f"Request failed: {e}")
        return False

def update_llm_model(model_name, api_key):
    """Update LLM model and API key."""
    try:
        payload = {"model_name": model_name, "api_key": api_key}
        response = requests.post("http://localhost:8001/mcp/change-lm", json=payload)
        
        if response.status_code == 200:
            return True
        else:
            st.error(f"Error changing LLM model: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        st.error(f"Request failed: {e}")
        return False

# --- Chat Management ---
def load_chat(chat_id):
    """Load a specific chat session."""
    if chat_id in st.session_state.chat_sessions:
        st.session_state.messages = st.session_state.chat_sessions[chat_id]["messages"]
        st.session_state.current_chat_name = st.session_state.chat_sessions[chat_id]["name"]
        st.session_state.current_chat_id = chat_id
    else:
        st.error("Chat session not found.")

def is_chat_modified(chat_id):
    """Check if the current chat is different from the saved version."""
    if chat_id is None:
        return True
        
    if chat_id not in st.session_state.chat_sessions:
        return True
        
    saved_messages = st.session_state.chat_sessions[chat_id]["messages"]
    current_messages = st.session_state.messages
    
    if len(saved_messages) != len(current_messages):
        return True
        
    for saved_msg, current_msg in zip(saved_messages, current_messages):
        if saved_msg["role"] != current_msg["role"] or saved_msg["content"] != current_msg["content"]:
            return True
            
    return False

def save_current_chat():
    """Save current chat if it contains messages and is modified."""
    if len(st.session_state.messages) == 0:
        return None
        
    if not is_chat_modified(st.session_state.current_chat_id):
        return st.session_state.current_chat_id
        
    chat_id = f"chat_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    default_name = get_chat_default_name()
    
    st.session_state.chat_sessions[chat_id] = {
        "messages": st.session_state.messages.copy(),
        "name": default_name,
        "timestamp": datetime.datetime.now()
    }
    st.session_state.current_chat_id = chat_id
    
    # Save to file whenever a new chat is created
    save_chat_sessions_to_file()
    return chat_id

def get_chat_default_name():
    """Generate a default name for the chat based on first message or timestamp."""
    default_name = "New Chat"
    if st.session_state.messages and st.session_state.messages[0]["role"] == "user":
        default_name = st.session_state.messages[0]["content"][:20] + "..."
    return default_name

def create_new_chat():
    """Create a new chat session."""
    save_current_chat()  # Save current chat before creating new one
    st.session_state.messages = []
    st.session_state.current_chat_name = None
    st.session_state.current_chat_id = None

def display_chat_history():
    """Display all stored chat sessions."""
    if not st.session_state.chat_sessions:
        st.write("No previous chats")
        return

    # Sort chats by timestamp, newest first
    sorted_chats = sorted(
        st.session_state.chat_sessions.items(),
        key=lambda x: x[1]["timestamp"],
        reverse=True
    )
    
    for chat_id, chat_data in sorted_chats:
        button_key = f"btn_{chat_id}"
        chat_name = chat_data["name"]
        button_text = f"📌 {chat_name}" if chat_id == st.session_state.current_chat_id else chat_name
        
        if st.button(button_text, key=button_key, use_container_width=True, icon="📁"):
            if st.session_state.current_chat_id != chat_id:
                save_current_chat()
            load_chat(chat_id)
            st.rerun()

def handle_chat_interface():
    """Display chat messages and handle new user input."""
    # Display existing messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Get and process new user input
    prompt = st.chat_input("Ask a question about your JIRA tickets")
    if prompt:
        # Add and display user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Get and display assistant response
        with st.spinner("Thinking..."):
            response = send_request(prompt, st.session_state.messages)
        
        if response:
            assistant_response = response.get("result", "No result found in response")
            st.session_state.messages.append({"role": "assistant", "content": assistant_response})
            with st.chat_message("assistant"):
                st.markdown(assistant_response)
            
            # Auto-save chat
            auto_save_chat()

def auto_save_chat():
    """Save the current chat after getting a response."""
    if st.session_state.current_chat_id:
        st.session_state.chat_sessions[st.session_state.current_chat_id]["messages"] = st.session_state.messages.copy()
        st.session_state.chat_sessions[st.session_state.current_chat_id]["timestamp"] = datetime.datetime.now()
        # Save changes to file
        save_chat_sessions_to_file()
    else:
        save_current_chat()

# --- UI Components ---
def render_history_tab():
    """Render the chat history sidebar tab."""

    
    new_chat = st.button("New Chat", use_container_width=True, icon="➕", type="primary")
    if new_chat:
        create_new_chat()
        st.rerun()
    
    st.markdown("---")
    display_chat_history()
    st.markdown("---")
    
    # Add option to export/import chat sessions
    if st.button("Export Chat Sessions", icon="📤"):
        export_chat_sessions()
    
    uploaded_file = st.file_uploader("Import Chat Sessions", type=["json"], key="chat_import")
    if uploaded_file is not None:
        import_chat_sessions(uploaded_file)

def export_chat_sessions():
    """Export chat sessions to a downloadable file."""
    try:
        serialized = serialize_chat_sessions()
        json_data = json.dumps(serialized, indent=2)
        
        st.download_button(
            label="Download Chat Sessions",
            data=json_data,
            file_name=f"chat_sessions_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.json",
            mime="application/json"
        )
        st.success("Chat sessions exported successfully!")
    except Exception as e:
        st.error(f"Error exporting chat sessions: {e}")

def import_chat_sessions(uploaded_file):
    """Import chat sessions from an uploaded file."""
    try:
        # Read and parse the uploaded JSON file
        content = uploaded_file.read()
        serialized = json.loads(content)
        imported_sessions = deserialize_chat_sessions(serialized)
        
        # Merge with existing sessions (new sessions will overwrite existing ones with the same ID)
        st.session_state.chat_sessions.update(imported_sessions)
        
        # Save merged sessions to file
        save_chat_sessions_to_file()
        
        # Display success message
        st.success(f"Successfully imported {len(imported_sessions)} chat sessions!")
        
        # Refresh the UI
        st.rerun()
    except Exception as e:
        st.error(f"Error importing chat sessions: {e}")

def render_settings_tab():
    """Render the settings sidebar tab."""
    st.write("Configure your chat settings here.")
    
    # MCP Server settings
    mcp_server = st.text_area(
        label="MCP SERVER URL", 
        value="""{
          "mcpServers": {
            "puppeteer": {
              "command": "npx",
              "args": ["@playwright/mcp@latest"]
            }
          }
        }""", 
        key="mcp_server_url", 
        height=500, 
        help="Enter the MCP server here"
    )
    
    if st.button("Set MCP Server"):
        try:
            parsed_json = json.loads(mcp_server)
            if update_mcp_server(mcp_server):
                st.success("MCP server updated successfully!")
        except json.JSONDecodeError:
            st.error("Invalid JSON format in MCP server configuration.")

    # LLM Model settings
    llm_model = st.text_input(
        label="LLM Model", 
        value="gemini/gemini-2.0-flash", 
        help="Enter the LLM model name here"
    )
    
    api_key = st.text_input(
        label="API Key", 
        type="password", 
        help="Enter your API key here"
    )
    
    if st.button("Set LLM"):
        if not llm_model:
            st.error("Please enter a valid LLM model name.")
        elif update_llm_model(llm_model, api_key):
            st.success("LLM model changed successfully!")
    
    # Add settings section for data persistence
    st.subheader("Data Persistence Settings")
    if st.button("Clear All Chat History", type="primary", use_container_width=True):
        if st.button("Confirm deletion? This cannot be undone.", key="confirm_delete"):
            st.session_state.chat_sessions = {}
            save_chat_sessions_to_file()
            st.session_state.messages = []
            st.session_state.current_chat_name = None
            st.session_state.current_chat_id = None
            st.success("All chat history has been deleted.")
            st.rerun()

# --- Main Application ---
def main():
    st.title("DSPy MCP Chatbot")
    st.markdown("---")
    
    initialize_session_state()
    
    # Create sidebar tabs
    tab1, tab2 = st.sidebar.tabs(["Chat History", "Settings"])
    
    with tab1:
        render_history_tab()
    
    with tab2:
        render_settings_tab()
    
    handle_chat_interface()

if __name__ == "__main__":
    main()
