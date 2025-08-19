import streamlit as st
import bcrypt
from .database import get_db_connection

def hash_password(password):
    """Hash a password for storing"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(stored_password, provided_password):
    """Verify a stored password against one provided by user"""
    # Convert stored_password to bytes if it's a string
    if isinstance(stored_password, str):
        stored_password = stored_password.encode('utf-8')
    
    # Ensure provided_password is bytes
    provided_password = provided_password.encode('utf-8') if isinstance(provided_password, str) else provided_password
    
    return bcrypt.checkpw(provided_password, stored_password)

def login_user(username, password):
    """Authenticate a user and return user data if successful"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get user from database
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()
    
    if user and verify_password(user['password'], password):
        # Store user info in session state
        st.session_state['authenticated'] = True
        st.session_state['user'] = {
            'id': user['id'],
            'username': user['username'],
            'full_name': user['full_name'],
            'role': user['role'],
            'department': user['department']
        }
        return True
    return False

def logout_user():
    """Log out the current user"""
    st.session_state['authenticated'] = False
    if 'user' in st.session_state:
        del st.session_state['user']

def require_auth():
    """Require authentication to access a page"""
    if not st.session_state.get('authenticated', False):
        st.warning('You need to log in to access this page.')
        st.stop()

def require_role(roles):
    """Require specific role(s) to access a page"""
    require_auth()
    user_role = st.session_state['user']['role']
    if isinstance(roles, str):
        roles = [roles]
    
    if user_role not in roles:
        st.error('You do not have permission to access this page.')
        st.stop()

def create_user(username, password, full_name, role, department=None):
    """Create a new user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    hashed_password = hash_password(password)
    
    try:
        cursor.execute(
            'INSERT INTO users (username, password, full_name, role, department) VALUES (?, ?, ?, ?, ?)',
            (username, hashed_password, full_name, role, department)
        )
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    
    conn.close()
    return success

def register_user(username, password, full_name, role, department_id=None):
    """
    Register a new user in the database
    
    Args:
        username (str): Username for the new user
        password (str): Password for the new user
        full_name (str): Full name of the new user
        role (str): Role of the new user (admin, staff, etc.)
        department_id (int, optional): Department ID for the new user
        
    Returns:
        tuple: (success, message)
    """
    import bcrypt
    from utils.database import get_db_connection
    
    # Check if username already exists
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    existing_user = cursor.fetchone()
    
    if existing_user:
        conn.close()
        return False, "Username sudah digunakan"
    
    try:
        # Hash the password
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        # Check the actual column names in the users table
        cursor.execute("PRAGMA table_info(users)")
        columns = cursor.fetchall()
        column_names = [column[1] for column in columns]
        
        # Determine the correct password column name
        password_column = "password_hash" if "password_hash" in column_names else "password"
        
        # Determine the correct department column name
        department_column = "department_id" if "department_id" in column_names else "department"
        
        # Construct the SQL query dynamically based on the column names
        query = f"""
            INSERT INTO users (username, {password_column}, full_name, role, {department_column})
            VALUES (?, ?, ?, ?, ?)
        """
        
        cursor.execute(query, (username, hashed_password, full_name, role, department_id))
        
        conn.commit()
        conn.close()
        
        return True, "Pengguna baru berhasil didaftarkan"
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, f"Error: {str(e)}"