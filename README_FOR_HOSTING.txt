DEPLOYMENT INSTRUCTIONS
=======================

APPLICATION OVERVIEW
--------------------
This is a Python Flask web application for Asset Management.
It uses SQLite as a database and Waitress as a production-grade WSGI server.

FILES & FOLDERS
---------------
- app.py: Main application logic.
- run_waitress.py: Entry point to start the server using Waitress.
- requirements.txt: List of Python dependencies.
- templates/: HTML templates.
- static/: CSS, JS, and images.
- instance/: Contains the database (inventory.db) and user uploads (uploads/).
  **IMPORTANT**: The 'instance' folder must be writable by the application.

HOW TO RUN (Linux/VPS)
----------------------
1. Install Python 3.8 or higher.
2. Create a virtual environment:
   python3 -m venv venv
   source venv/bin/activate
3. Install dependencies:
   pip install -r requirements.txt
4. Run the application:
   python run_waitress.py
   
   OR use Gunicorn (recommended for Linux):
   pip install gunicorn
   gunicorn -w 4 -b 0.0.0.0:8000 app:app

HOW TO RUN (cPanel/Python App)
------------------------------
1. Create a Python Application in cPanel.
2. Set Application root to the uploaded folder.
3. Set Application entry point to `app.py` and Callable to `app`.
4. Install dependencies from `requirements.txt`.

PERSISTENCE
-----------
- Database is at `instance/inventory.db`.
- Uploaded files are at `instance/uploads/`.
Ensure these paths are persisted and backed up.

ENVIRONMENT VARIABLES
---------------------
(Optional)
- SECRET_KEY: Change this in app.py for production security.
