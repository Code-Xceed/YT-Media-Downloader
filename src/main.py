import sys
import os

# Ensure the app can find the core and ui modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.app import App

if __name__ == "__main__":
    app = App()
    app.mainloop()
