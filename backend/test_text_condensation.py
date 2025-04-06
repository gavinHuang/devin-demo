import json
import requests
import os

with open('sample_anthropic_article.txt', 'r') as f:
    sample_text = f.read()

payload = {
    "text": sample_text,
    "percentage": 50,
    "preserve_headings": True
}

try:
    response = requests.post(
        "http://localhost:8000/api/condense-text",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"Status code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print("\nCondensation Results:")
        print(f"Original length: {result['original_length']} characters")
        print(f"Condensed length: {result['condensed_length']} characters")
        print(f"Percentage achieved: {result['percentage_achieved']:.2f}%")
        print("\nCondensed Text:")
        print(result['condensed_text'])
        
        with open('/tmp/condensed_result.json', 'w') as f:
            json.dump(result, f, indent=2)
        print("\nFull result saved to /tmp/condensed_result.json")
    else:
        print(f"Error: {response.text}")
except Exception as e:
    print(f"Exception: {str(e)}")
