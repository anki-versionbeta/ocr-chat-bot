import subprocess
import sys
import os

"""
This script installs all required dependencies for the OCR Chatbot backend.
Run this script before starting the backend server.
"""

def install_dependencies():
    print("Installing required packages...")
    try:
        # Install packages from requirements.txt
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("Successfully installed packages from requirements.txt")
        
        # Additional packages that might be needed
        additional_packages = [
            "numpy",
            "pandas",
            "openpyxl",
            "boto3",
            "pymupdf",
            "pypdf2",
            "fuzzywuzzy",
            "python-levenshtein",
            "flask",
            "stomp-py",
            "python-decouple",
            "pdfplumber",
            "pdf2image",
            "PyCryptodome"
        ]
        
        for package in additional_packages:
            try:
                print(f"Installing {package}...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                print(f"Successfully installed {package}")
            except Exception as e:
                print(f"Error installing {package}: {e}")
        
        print("\nAll dependencies installed successfully!")
        print("You can now run the backend server with: python app.py")
        
    except Exception as e:
        print(f"Error installing dependencies: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("OCR Chatbot Backend - Dependency Installer")
    print("==========================================")
    
    # Check if requirements.txt exists
    if not os.path.exists("requirements.txt"):
        print("Error: requirements.txt not found in the current directory.")
        print(f"Current directory: {os.getcwd()}")
        print("Please run this script from the backend directory.")
        sys.exit(1)
    
    # Install dependencies
    success = install_dependencies()
    
    if success:
        print("\nSetup complete!")
    else:
        print("\nSetup failed. Please check the error messages above.")
        sys.exit(1) 