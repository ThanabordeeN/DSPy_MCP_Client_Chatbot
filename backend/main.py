import os
from contextlib import asynccontextmanager
from typing import Dict, List, Any, Optional
import logging
# Third-party imports
import dspy


import litellm
from fastapi import FastAPI, Body, HTTPException
from pydantic import BaseModel
import json

# Configure litellm callbacks
litellm.success_callback = ["langfuse"]
litellm.failure_callback = ["langfuse"]

# Configuration settings
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(CURRENT_DIR, "servers_config.json")
LM_MODEL = "gemini/gemini-2.0-flash"
DEFAULT_PORT = 8001
MAX_ITERATIONS = 7
# Set logging level for MCP client
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_client")

# Define models
class MultiServerSignature(dspy.Signature):
    """Helpful Assistant with Tools Available"""
    history: List[Dict[str, str]] = dspy.InputField(desc="The conversation history.")
    user_input: str = dspy.InputField(desc="The user's request, potentially requiring external tools.")
    output: str = dspy.OutputField(desc="The final response to the user should be in natural language.")

class QueryRequest(BaseModel):
    query: str = "Hello, how can I help you?"
    history: List[Dict[str, str]] = []

class LMChangeRequest(BaseModel):
    model_name: str
    api_key: Optional[str] = None

class MCPService:
    """Service class to manage MCP functionality"""
    
    def __init__(self):
        self.lm = None
        self.server_manager = None
        self.react_agent = None
        self.all_mcp_tools = None
        
    async def update_setup_mcp(self, config_file: str) -> dspy.MCPServerManager:
        """Setup MCP server manager and initialize servers."""
        self.server_manager = dspy.MCPServerManager()
        logging.info("Setting up MCP server manager")
        
        try:
            config = config_file
            await self.server_manager.initialize_servers(config)
            logging.info("MCP server manager initialized successfully")
            return self.server_manager
        except Exception as e:
            print(f"Error setting up MCP: {str(e)}")
            raise
    
    async def get_all_tools(self) -> list:
        """Get all available tools from the MCP server manager."""
        if not self.server_manager:
            raise ValueError("Server manager not initialized")
        logging.info("Getting all tools from MCP server manager")
        
        try:
            all_tools = await self.server_manager.get_all_tools()
            logging.info(f"Retrieved {len(all_tools)} tools")
            return all_tools
        except Exception as e:
            print(f"Error getting tools: {str(e)}")
            raise
    
    
    async def update_config(self, config: dict) -> None:
        """Update the MCP configuration."""
        logging.info("Updating MCP configuration")
        try:
            self.server_manager = await self.update_setup_mcp(config_file=config)
            self.all_mcp_tools = await self.get_all_tools()
            self.react_agent = dspy.ReAct(
                MultiServerSignature,
                tools=self.all_mcp_tools,
                max_iters=MAX_ITERATIONS
            )
            logging.info("MCP configuration updated successfully")
        except Exception as e:
            print(f"Config update error: {str(e)}")
            raise
    
    async def process_query(self, query: str , history:List[Dict[str, str]]) -> str:
        """Process a user query using the reactive agent."""
        logging.info(f"Processing query: {query} with history: {history}")
        if not self.react_agent:
            raise ValueError("Reactive agent not initialized")
        
        try:
            result = await self.react_agent.async_forward(
                user_input=query, 
                history=history
            )
            
            return result.output
        except Exception as e:
            print(f"Query processing error: {str(e)}")
            raise

    async def update_lm(self, model_name: str, api_key: Optional[str] = None) -> None:
        """Update the language model being used."""
        try:
            # Use provided API key or fall back to environment variable
            actual_api_key = api_key if api_key else os.getenv("GOOGLE_API_KEY")
            logging.info("updating language model")
            
            # Initialize the new language model
            self.lm = dspy.LM(model_name, api_key=actual_api_key)
            dspy.configure(lm=self.lm)

            
            # Re-initialize the reactive agent with the new LM
            if self.all_mcp_tools:
                self.react_agent = dspy.ReAct(
                    MultiServerSignature,
                    tools=self.all_mcp_tools,
                    max_iters=MAX_ITERATIONS
                )
            logging.info("Language model updated successfully")
                
            return self.lm
        except Exception as e:
            print(f"Error updating language model: {str(e)}")
            raise

# Create MCP service instance
mcp_service = MCPService()

# FastAPI lifespan handler
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for the FastAPI application."""
    print("Starting up MCP API server...")
    
    try:
        await mcp_service.initialize()
    except Exception as e:
        print(f"Failed to initialize MCP service: {str(e)}")
    
    yield
    
    # Shutdown: Clean up resources
    print("Shutting down MCP API server...")
    if mcp_service.server_manager:
        await mcp_service.server_manager.cleanup()
    print("Shutdown complete")

# Create FastAPI app
app = FastAPI(
    title="MCP API", 
    description="API for MCP AIR BNB server", 
    version="0.1.0",
    lifespan=lifespan
)

@app.post("/mcp/query")
async def process_query(request: QueryRequest = Body(...)):
    """Process a query using the MCP server."""
    try:
        result = await mcp_service.process_query(request.query, request.history)
        return {"result": result}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"Service configuration error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query processing error: {str(e)}")
    
@app.post("/mcp/update")
async def update_config(config: Dict[str, Any] = Body(...)):
    """Update the MCP server configuration."""
    config = json.loads(config['mcp_server'])
    try:
        await mcp_service.update_config(config)
        return {"status": "Configuration updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Config update error: {str(e)}")

@app.post("/mcp/change-lm")
async def change_language_model(request: LMChangeRequest = Body(...)):
    """Change the language model being used by the service."""
    try:
        await mcp_service.update_lm(request.model_name, request.api_key)
        return {
            "status": "Language model updated successfully",
            "model": request.model_name
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Language model update error: {str(e)}")

# For running with uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=DEFAULT_PORT, reload=False)