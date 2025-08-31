"""
Final cleanup to remove orphaned streaming response blocks
"""
import re

def final_streaming_cleanup():
    with open('python-api/main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_lines = len(content.split('\n'))
    
    # Remove orphaned streaming response blocks
    # Find and remove the first orphaned streaming block (around line 3488-3536)
    content = re.sub(
        r'# /refreshdb-progress-stream endpoint removed\}\n\n".*?'
        r'return StreamingResponse\([^)]+\)(?:\s*})?',
        '# Progress streaming endpoints removed',
        content,
        flags=re.DOTALL
    )
    
    # Remove any remaining orphaned streaming response blocks
    content = re.sub(
        r'async def generate\(\):.*?return StreamingResponse\([^)]+\)',
        '# Streaming response removed',
        content,
        flags=re.DOTALL
    )
    
    # Clean up any malformed function definitions left behind
    content = re.sub(r'^\s*async def generate\(\):.*?yield.*?(?=^[a-zA-Z]|\Z)', 
                     '', content, flags=re.MULTILINE | re.DOTALL)
    
    # Remove import of StreamingResponse if no longer used
    remaining_streaming = content.count('StreamingResponse')
    if remaining_streaming <= 1:  # Only the import line
        content = re.sub(
            r'from fastapi\.responses import JSONResponse, StreamingResponse',
            'from fastapi.responses import JSONResponse',
            content
        )
    
    # Clean up any multiple empty lines
    content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
    
    # Save the cleaned content
    with open('python-api/main.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    new_lines = len(content.split('\n'))
    print(f"Final streaming cleanup completed. Lines reduced from {original_lines} to {new_lines}")
    
    # Check remaining streaming references
    remaining_streaming_final = content.count('StreamingResponse')
    print(f"Remaining 'StreamingResponse' references: {remaining_streaming_final}")

if __name__ == '__main__':
    final_streaming_cleanup()