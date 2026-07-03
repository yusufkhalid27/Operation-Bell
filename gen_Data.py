import random
import string

DEFAULT_EMAIL = "liamprint4@gmail.com"

def generate_email(email: str = DEFAULT_EMAIL) -> str:
    # Generate a unique email address by appending a random string to the default email

    random_string = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    email_parts = email.split('@')
    unique_email = f"{email_parts[0]}+{random_string}@{email_parts[1]}"
    
    return unique_email

def generate_first_last_name():
    with open("names.txt", "r") as f:
        names = [line.strip() for line in f if line.strip()]
    first_name = random.choice(names)
    last_name = random.choice(string.ascii_letters.capitalize())
    return first_name, last_name