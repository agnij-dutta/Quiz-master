from app import create_app, db
from app.models import Admin

app = create_app()

with app.app_context():
    # Create all tables
    db.create_all()
    
    # Create default admin if it doesn't exist
    admin = Admin.query.filter_by(username='admin').first()
    if not admin:
        admin = Admin(username='admin')
        admin.set_password('admin123')  # Default password
        db.session.add(admin)
        db.session.commit()
        print("Default admin account created.")
    else:
        print("Admin account already exists.")
