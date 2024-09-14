# database.py

import sqlite3
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Database filename
DB_FILENAME = 'bot_database.db'

def initialize_database():
    """Initialize the SQLite database and create the users table."""
    conn = sqlite3.connect(DB_FILENAME)
    cursor = conn.cursor()
    
    # Create users table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            free_interactions_used INTEGER DEFAULT 0,
            stars INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.debug("Database initialized and users table ensured.")

def get_user(user_id):
    """Retrieve user data from the database."""
    conn = sqlite3.connect(DB_FILENAME)
    cursor = conn.cursor()
    
    cursor.execute('SELECT free_interactions_used, stars FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if result:
        user_data = {'free_interactions_used': result[0], 'stars': result[1]}
    else:
        # If user doesn't exist, create a new record
        cursor.execute('INSERT INTO users (user_id) VALUES (?)', (user_id,))
        conn.commit()
        user_data = {'free_interactions_used': 0, 'stars': 0}
    
    conn.close()
    logger.debug(f"Retrieved user {user_id}: {user_data}")
    return user_data

def update_user(user_id, free_interactions_used=None, stars=None):
    """Update user data in the database."""
    conn = sqlite3.connect(DB_FILENAME)
    cursor = conn.cursor()
    
    if free_interactions_used is not None and stars is not None:
        cursor.execute('''
            UPDATE users
            SET free_interactions_used = ?, stars = ?
            WHERE user_id = ?
        ''', (free_interactions_used, stars, user_id))
    elif free_interactions_used is not None:
        cursor.execute('''
            UPDATE users
            SET free_interactions_used = ?
            WHERE user_id = ?
        ''', (free_interactions_used, user_id))
    elif stars is not None:
        cursor.execute('''
            UPDATE users
            SET stars = ?
            WHERE user_id = ?
        ''', (stars, user_id))
    
    conn.commit()
    conn.close()
    logger.debug(f"Updated user {user_id}: free_interactions_used={free_interactions_used}, stars={stars}")

def add_stars(user_id, stars_to_add):
    """Add stars to a user's balance."""
    user = get_user(user_id)
    new_stars = user['stars'] + stars_to_add
    update_user(user_id, stars=new_stars)
    logger.debug(f"Added {stars_to_add} stars to user {user_id}. New balance: {new_stars}")

def consume_star(user_id):
    """Consume one star from a user's balance."""
    user = get_user(user_id)
    if user['stars'] > 0:
        new_stars = user['stars'] - 1
        update_user(user_id, stars=new_stars)
        logger.debug(f"Consumed 1 star from user {user_id}. Remaining stars: {new_stars}")
        return True
    else:
        logger.debug(f"User {user_id} has no stars to consume.")
        return False

def increment_free_interactions(user_id):
    """Increment the count of free interactions used by the user."""
    user = get_user(user_id)
    new_free = user['free_interactions_used'] + 1
    update_user(user_id, free_interactions_used=new_free)
    logger.debug(f"Incremented free interactions for user {user_id}. Total used: {new_free}")
    return new_free
