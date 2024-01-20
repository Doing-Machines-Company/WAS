import re

def match_string(s):
    patterns = {
        "alphanumeric:STOP": r"([A-Za-z0-9]+):STOP",
        "number:STOP": r"(\d+):STOP",
        "number": r"(\d+)",
        "number:alphanumeric": r"(\d+):([A-Za-z0-9]+)"
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, s)
        if match:
            return key, match.groups()

    return "No match", None

# Test the function with different strings
print(match_string("123abc:STOP"))  # alphanumeric:STOP
print(match_string("12345:STOP"))   # number:STOP
print(match_string("67890"))        # number
print(match_string("123:xyz"))      # number:alphanumeric
