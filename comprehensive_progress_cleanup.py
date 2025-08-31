"""
Comprehensive cleanup to remove all remaining progress-related endpoints
"""
import re

def comprehensive_cleanup():
    with open('python-api/main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_lines = len(content.split('\n'))
    
    # Remove csv-upload-progress endpoint
    content = re.sub(
        r'@app\.get\("/csv-upload-progress"\)\s*\n'
        r'async def get_csv_upload_progress\(\):[^@]*?return \{[^}]*\}',
        '# CSV upload progress endpoint removed',
        content,
        flags=re.DOTALL
    )
    
    # Remove csv-upload-progress-stream endpoint
    content = re.sub(
        r'@app\.get\("/csv-upload-progress-stream"\)\s*\n'
        r'async def csv_upload_progress_stream\(\):[^@]*?(?=@|\Z)',
        '# CSV upload progress stream endpoint removed\n',
        content,
        flags=re.DOTALL
    )
    
    # Remove any remaining progress_queue references
    content = re.sub(r'.*progress_queue\.empty\(\).*\n', '', content)
    content = re.sub(r'.*progress_queue\.get.*\n', '', content)
    
    # Remove any remaining current_progress references
    content = re.sub(r'.*current_progress.*\n', '', content)
    
    # Clean up any multiple empty lines
    content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
    
    # Save the cleaned content
    with open('python-api/main.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    new_lines = len(content.split('\n'))
    print(f"Comprehensive cleanup completed. Lines reduced from {original_lines} to {new_lines}")
    
    # Check for remaining problematic references
    remaining_progress = content.count('progress_queue')
    remaining_current = content.count('current_progress')
    remaining_stream = content.count('progress-stream')
    
    print(f"Remaining 'progress_queue' references: {remaining_progress}")
    print(f"Remaining 'current_progress' references: {remaining_current}")
    print(f"Remaining 'progress-stream' references: {remaining_stream}")

if __name__ == '__main__':
    comprehensive_cleanup()