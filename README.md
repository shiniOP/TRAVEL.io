...................................................................................................................................................................
✈️ TRAVEL.io — AI Multi-Agent Travel Planner

TRAVEL.io is an AI-powered multi-agent travel planning platform that turns natural-language travel requests into practical, budget-aware itineraries. It combines LangGraph, MCP, Groq, FastAPI, PostgreSQL, and Docker to coordinate specialized travel agents and external tools.

🌐 Live Demo: https://travel-io-yuj6.onrender.com

🚀 Features
🤖 Multi-Agent AI Architecture
Flight Agent
Hotel Agent
Weather Agent
Budget Agent
Itinerary Agent
Final Response Agent
🧠 LangGraph Workflow
State-based agent orchestration
Sequential multi-agent execution
Persistent workflow state
🔌 Model Context Protocol (MCP)
Tavily MCP — travel and hotel information
AviationStack MCP — airport and flight information
Custom Weather MCP — current weather and forecasts using OpenWeather
👤 Human-in-the-Loop (HITL)
Generates a draft itinerary
User can approve the draft
User can provide revision feedback
Workflow resumes with the feedback
🛡️ Guardrails & Supervisor
Validates travel requests
Determines the appropriate agents for the request
Prevents unsuitable requests from entering the workflow
💰 Budget Planning
Considers the user's specified budget
Produces budget-aware recommendations
🌦️ Weather-Aware Planning
Retrieves current weather
Retrieves forecasts
Incorporates weather information into itinerary recommendations
💾 PostgreSQL Persistence
LangGraph PostgreSQL checkpointer
Thread-based conversations
Persistent workflow state
🌐 FastAPI Backend
REST API endpoints
Async-compatible MCP integrations
Interactive API documentation
🎨 Modern Web Interface
Responsive travel-planning UI
Agent execution visualization
Markdown-rendered results
Copy travel plan
PDF export
🐳 Dockerized
Reproducible application environment
Ready for cloud deployment
☁️ Cloud Deployment
Deployed using Docker on Render

...................................................................................................................................................................
