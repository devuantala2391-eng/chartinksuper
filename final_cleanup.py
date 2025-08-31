"""
Final cleanup to remove all progress-related endpoints and references
"""
import re

def final_cleanup():
    with open('python-api/main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Remove refreshdb-progress endpoints and references
    content = re.sub(r'@app\.get\("/refreshdb-progress"\).*?return current_progress', 
                     '# /refreshdb-progress endpoint removed', content, flags=re.DOTALL)
    
    content = re.sub(r'@app\.get\("/refreshdb-progress-stream"\).*?}\s*\)', 
                     '# /refreshdb-progress-stream endpoint removed', content, flags=re.DOTALL)
    
    # Remove progress URL references
    content = re.sub(r'.*"progressUrl": "/refreshdb-progress".*\n', '', content)
    content = re.sub(r'.*Check progress at /refreshdb-progress.*', 
                     'Database refresh completed', content)
    
    # Remove SSE progress print statement
    content = re.sub(r'.*SSE Progress: GET.*refreshdb-progress-stream.*\n', 
                     '    # SSE Progress endpoint removed\n', content)
    
    # Remove any remaining current_progress references that cause errors
    content = re.sub(r'.*return current_progress.*\n', 
                     '    return {"status": "completed"}\n', content)
    
    # Clean up any double empty lines
    content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
    
    # Save the cleaned content
    with open('python-api/main.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("Final cleanup completed")
    
    # Check for remaining progress references
    remaining = content.count('progress')
    print(f"Remaining 'progress' references: {remaining}")
    
    # Check for remaining current_progress references
    remaining_current = content.count('current_progress')
    print(f"Remaining 'current_progress' references: {remaining_current}")

if __name__ == '__main__':
    final_cleanup()