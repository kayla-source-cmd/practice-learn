from ai_helper import get_ai_suggestions

description = (
    "My laptop cannot connect to the office Wi-Fi, "
    "but other devices can connect successfully."
)

print("\nTesting Gemini AI...\n")

suggestions = get_ai_suggestions(description)

if suggestions:
    print("AI Suggestions:")
    print(suggestions)
else:
    print("No AI suggestions received.")