# Quiz Master

A multi-user quiz platform built with Flask for exam preparation across multiple courses.

## Features

- Multi-user support with admin and regular user roles
- Subject and chapter management
- Quiz creation and management
- User registration and authentication
- Quiz attempt tracking and scoring
- Bootstrap-based responsive UI

## Setup Instructions

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Linux/Mac
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python app.py
```

The application will be available at `http://localhost:5000`

## Default Admin Credentials

- Username: admin
- Password: admin123

## Project Structure

- `app.py`: Main application file with routes and configuration
- `models.py`: Database models
- `templates/`: HTML templates
- `requirements.txt`: Python dependencies

## Technologies Used

- Flask
- SQLAlchemy
- Flask-Login
- Bootstrap
- SQLite
