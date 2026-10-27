import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")


def get_ai_suggestions(description):
    """Send a ticket description to Gemini and return suggestions."""

    if not api_key:
        print("AI suggestions unavailable: Gemini API key not found.")
        return None

    try:
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=(
                "You are a helpful IT support assistant. "
                "Analyze this support ticket and provide: "
                "1. A brief summary of the problem. "
                "2. Possible causes. "
                "3. Recommended troubleshooting steps. "
                "4. Suggested priority: low, medium, high, or critical.\n\n"
                f"Ticket description: {description}"
            ),
        )

        if response.text:
            return response.text

        print("AI did not return any suggestions.")
        return None

    except Exception as error:
        print(f"AI suggestions unavailable: {error}")
        return None