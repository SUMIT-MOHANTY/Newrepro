import requests
import os

BASE_URL = "http://localhost:8000"

def test_signup():
    print("Testing Signup...")
    payload = {
        "email": "test@example.com",
        "first_name": "Test",
        "last_name": "User",
        "organization_name": "Test Organization",
    }
    try:
        response = requests.post(f"{BASE_URL}/users/", json=payload)
        if response.status_code == 200:
            print("Signup Success:", response.json())
            print("Password was sent by email.")
            return True
        elif response.status_code == 400 and "Email already registered" in response.text:
            print("User already exists.")
            return True
        else:
            print("Signup Failed:", response.status_code, response.text)
            return False
    except Exception as e:
        print("Signup Error:", e)
        return False

def test_login():
    print("\nTesting Login...")
    emailed_password = os.getenv("TEST_LOGIN_PASSWORD")
    if not emailed_password:
        print("Skipping login test. Set TEST_LOGIN_PASSWORD to the emailed password to verify login.")
        return None

    payload = {"username": "test@example.com", "password": emailed_password}
    try:
        response = requests.post(f"{BASE_URL}/token", data=payload)
        if response.status_code == 200:
            token = response.json().get("access_token")
            print("Login Success. Token:", token[:20] + "...")
            return token
        else:
            print("Login Failed:", response.status_code, response.text)
            return None
    except Exception as e:
        print("Login Error:", e)
        return None

def test_me(token):
    print("\nTesting Get Current User...")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(f"{BASE_URL}/users/me", headers=headers)
        if response.status_code == 200:
            print("User Info:", response.json())
        else:
            print("Get User Failed:", response.status_code, response.text)
    except Exception as e:
        print("Get User Error:", e)

if __name__ == "__main__":
    if test_signup():
        token = test_login()
        if token:
            test_me(token)
