import msal
tenant = "e0472950-72a7-456f-9ef1-23c644042bfd"
client_id = "677df157-25b9-4eb3-b01a-5b26cc4bfb6d"

app = msal.PublicClientApplication(client_id, authority=f"https://login.microsoftonline.com/{tenant}")
print("Public client test complete")
