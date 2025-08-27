"""
Example usage of the AI Voice Assistant classes
"""

from ai_processor import VoiceAssistant, AudioProcessor, LLMProcessor, CalendarManager, AppointmentProcessor


def example_basic_usage():
    """Basic example of using the VoiceAssistant"""
    print("=== Basic Voice Assistant Usage ===")
    
    # Create voice assistant instance
    voice_assistant = VoiceAssistant(voice_response=False)  # Disable TTS for this example
    
    # Process a voice file (assuming you have one)
    # response = voice_assistant.process_voice_input("path/to/audio.wav")
    # print(f"AI Response: {response}")
    
    print("Voice Assistant initialized successfully!")


def example_individual_components():
    """Example of using individual components"""
    print("\n=== Individual Components Usage ===")
    
    # Audio Processing
    audio_processor = AudioProcessor()
    print(f"Audio processor configured: {audio_processor.sample_rate}Hz, {audio_processor.channels} channels")
    
    # LLM Processing
    llm_processor = LLMProcessor()
    print(f"LLM processor configured: {llm_processor.model_name}")
    
    # Test LLM response
    test_prompt = "Schedule a meeting for tomorrow at 2 PM"
    try:
        response = llm_processor.extract_appointment_details(test_prompt)
        print(f"LLM extracted details: {response}")
    except Exception as e:
        print(f"LLM test failed: {e}")
    
    # Calendar Management
    calendar_manager = CalendarManager()
    print(f"Calendar manager configured: {calendar_manager.timezone}, working hours: {calendar_manager.working_hours}")
    
    # Appointment Processing
    appointment_processor = AppointmentProcessor()
    print(f"Appointment processor configured: {appointment_processor.appointment_duration} minutes")


def example_custom_configuration():
    """Example of custom configuration"""
    print("\n=== Custom Configuration Example ===")
    
    # Custom audio settings
    custom_audio = AudioProcessor(
        sample_rate=16000,  # Lower sample rate for faster processing
        channels=1,
        record_seconds=10
    )
    print(f"Custom audio: {custom_audio.sample_rate}Hz, {custom_audio.record_seconds}s")
    
    # Custom LLM settings
    custom_llm = LLMProcessor(
        api_url="http://localhost:11434/api/generate",
        model_name="llama2:7b"  # Different model
    )
    print(f"Custom LLM: {custom_llm.model_name}")
    
    # Custom calendar settings
    custom_calendar = CalendarManager(
        timezone="Europe/London",
        working_hours=(8, 18)  # 8 AM to 6 PM
    )
    print(f"Custom calendar: {custom_calendar.timezone}, hours: {custom_calendar.working_hours}")


def example_error_handling():
    """Example of error handling"""
    print("\n=== Error Handling Example ===")
    
    try:
        # Try to authenticate with calendar (this will likely fail without proper setup)
        calendar_manager = CalendarManager()
        service = calendar_manager.authenticate()
        print("Calendar authentication successful!")
    except Exception as e:
        print(f"Calendar authentication failed (expected): {e}")
    
    try:
        # Try to transcribe a non-existent file
        audio_processor = AudioProcessor()
        transcript = audio_processor.transcribe_with_whisper("non_existent_file.wav")
        print(f"Transcript: {transcript}")
    except Exception as e:
        print(f"Transcription failed (expected): {e}")


if __name__ == "__main__":
    print("AI Voice Assistant - Example Usage")
    print("=" * 50)
    
    example_basic_usage()
    example_individual_components()
    example_custom_configuration()
    example_error_handling()
    
    print("\n" + "=" * 50)
    print("Examples completed! Check the output above for details.")
