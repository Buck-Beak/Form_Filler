import sys

path = r"c:\Users\abhij\OneDrive\Desktop\finalYearProject\Form_Filler\navigation_agent.py"
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace non-ASCII characters and special box-drawing characters
cleaned = content.encode('ascii', 'ignore').decode('ascii')

with open(path, 'w', encoding='ascii') as f:
    f.write(cleaned)

print("Scrubbed non-ASCII characters from NavigationAgent.py")
