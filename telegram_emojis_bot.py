from flask import Flask, render_template_string
import random
import string

app = Flask(__name__)

# HTML template with embedded CSS and JavaScript
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>5-Letter Username Generator</title>
    <style>
        body {
            font-family: 'Arial', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            margin: 0;
            padding: 20px;
        }
        
        .container {
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            text-align: center;
            max-width: 400px;
            width: 100%;
        }
        
        h1 {
            color: #333;
            margin-bottom: 30px;
            font-size: 2em;
        }
        
        .username-display {
            background: #f8f9fa;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            padding: 20px;
            margin: 20px 0;
            font-size: 2em;
            font-weight: bold;
            letter-spacing: 3px;
            color: #495057;
            text-transform: uppercase;
        }
        
        .btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 15px 30px;
            margin: 10px;
            border-radius: 50px;
            cursor: pointer;
            font-size: 16px;
            font-weight: bold;
            transition: all 0.3s ease;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }
        
        .btn:active {
            transform: translateY(0);
        }
        
        .copy-btn {
            background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
        }
        
        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            background: #28a745;
            color: white;
            padding: 15px 20px;
            border-radius: 10px;
            opacity: 0;
            transition: opacity 0.3s ease;
            z-index: 1000;
        }
        
        .notification.show {
            opacity: 1;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎯 Username Generator</h1>
        <div class="username-display" id="username">{{ username }}</div>
        
        <button class="btn" onclick="refreshUsername()">
            🔄 Generate New
        </button>
        
        <button class="btn copy-btn" onclick="copyUsername()">
            📋 Copy Username
        </button>
    </div>
    
    <div class="notification" id="notification">
        Username copied to clipboard! 📋
    </div>

    <script>
        function refreshUsername() {
            fetch('/generate')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('username').textContent = data.username;
                })
                .catch(error => console.error('Error:', error));
        }
        
        function copyUsername() {
            const username = document.getElementById('username').textContent;
            navigator.clipboard.writeText(username).then(function() {
                showNotification();
            }, function(err) {
                console.error('Could not copy text: ', err);
                // Fallback for older browsers
                const textArea = document.createElement('textarea');
                textArea.value = username;
                document.body.appendChild(textArea);
                textArea.select();
                document.execCommand('copy');
                document.body.removeChild(textArea);
                showNotification();
            });
        }
        
        function showNotification() {
            const notification = document.getElementById('notification');
            notification.classList.add('show');
            setTimeout(() => {
                notification.classList.remove('show');
            }, 2000);
        }
        
        // Auto-refresh every 30 seconds (optional)
        // setInterval(refreshUsername, 30000);
    </script>
</body>
</html>
"""

def generate_username():
    """Generate a random 5-letter username"""
    # Mix of vowels and consonants for better readability
    vowels = 'aeiou'
    consonants = 'bcdfghjklmnpqrstvwxyz'
    
    # Create patterns for more pronounceable usernames
    patterns = [
        'cvcvc',  # consonant-vowel-consonant-vowel-consonant
        'vcvcv',  # vowel-consonant-vowel-consonant-vowel
        'cvccv',  # consonant-vowel-consonant-consonant-vowel
        'vccvc',  # vowel-consonant-consonant-vowel-consonant
    ]
    
    pattern = random.choice(patterns)
    username = ''
    
    for char in pattern:
        if char == 'c':
            username += random.choice(consonants)
        else:  # vowel
            username += random.choice(vowels)
    
    return username.upper()

@app.route('/')
def index():
    """Main page with initial username"""
    username = generate_username()
    return render_template_string(HTML_TEMPLATE, username=username)

@app.route('/generate')
def generate():
    """API endpoint to generate new username"""
    username = generate_username()
    return {'username': username}

if __name__ == '__main__':
    print("🚀 Starting 5-Letter Username Generator...")
    print("📱 Open your browser and go to: http://localhost:5000")
    print("🔄 Click 'Generate New' to create fresh usernames")
    print("📋 Click 'Copy Username' to copy to clipboard")
    print("⏹️  Press Ctrl+C to stop the server")
    
    app.run(debug=True, host='0.0.0.0', port=5000)