import subprocess
import time

def type_text_in_active_window(text):
    try:
        # Wait a moment to ensure the active window is ready
        time.sleep(0.5)

        # Use xdotool to type text into the active window
        subprocess.run(["xdotool", "type", text], check=True)
        subprocess.run(["xdotool", "key", "Return"], check=True)

    except FileNotFoundError:
        print("Error: xdotool is not installed. Install it using 'sudo apt install xdotool'.")
    except subprocess.CalledProcessError as e:
        print(f"Error running xdotool: {e}")

if __name__ == "__main__":
    # Text to output under the active prompt
    text_to_type = "Hello from Python!"

    print("Switch to the window where you want the output within 5 seconds...")
    time.sleep(5)  # Give the user time to focus the desired window

    type_text_in_active_window(text_to_type)