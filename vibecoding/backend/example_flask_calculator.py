from flask import Flask, request, render_template_string
import re

app = Flask(__name__)

# HTML template for the calculator
CALCULATOR_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Advanced Calculator</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        
        .calculator {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
            max-width: 400px;
            width: 100%;
        }
        
        .display {
            background: #1a1a1a;
            color: #ffffff;
            font-size: 2.5rem;
            padding: 20px;
            text-align: right;
            border-radius: 10px;
            margin-bottom: 20px;
            min-height: 80px;
            word-wrap: break-word;
            overflow-wrap: break-word;
        }
        
        .buttons {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
            margin-bottom: 20px;
        }
        
        .btn {
            background: #2d2d2d;
            color: #ffffff;
            border: none;
            padding: 20px;
            font-size: 1.2rem;
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        
        .btn:hover {
            background: #404040;
            transform: translateY(-2px);
        }
        
        .btn:active {
            transform: translateY(0);
        }
        
        .btn.operator {
            background: #ff6b6b;
        }
        
        .btn.operator:hover {
            background: #ff8787;
        }
        
        .btn.equals {
            background: #4ecdc4;
            grid-column: span 2;
        }
        
        .btn.equals:hover {
            background: #45b7aa;
        }
        
        .btn.clear {
            background: #e74c3c;
            grid-column: span 2;
        }
        
        .btn.clear:hover {
            background: #c0392b;
        }
        
        .btn.zero {
            grid-column: span 2;
        }
        
        .history {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            padding: 15px;
            margin-top: 20px;
            max-height: 150px;
            overflow-y: auto;
        }
        
        .history-item {
            background: rgba(255, 255, 255, 0.05);
            padding: 8px;
            margin-bottom: 5px;
            border-radius: 5px;
            font-size: 0.9rem;
            color: #cccccc;
        }
        
        .title {
            text-align: center;
            color: #ffffff;
            margin-bottom: 20px;
            font-size: 1.5rem;
            font-weight: 300;
        }
        
        @media (max-width: 480px) {
            .calculator {
                padding: 20px;
                margin: 10px;
            }
            
            .btn {
                padding: 15px;
                font-size: 1rem;
            }
            
            .display {
                font-size: 2rem;
                min-height: 60px;
            }
        }
    </style>
</head>
<body>
    <div class="calculator">
        <h1 class="title">Advanced Calculator</h1>
        <div class="display" id="display">0</div>
        <div class="buttons">
            <button class="btn clear" onclick="clearDisplay()">C</button>
            <button class="btn operator" onclick="appendToDisplay('/')">/</button>
            <button class="btn operator" onclick="appendToDisplay('*')">×</button>
            <button class="btn operator" onclick="deleteLast()">⌫</button>
            
            <button class="btn" onclick="appendToDisplay('7')">7</button>
            <button class="btn" onclick="appendToDisplay('8')">8</button>
            <button class="btn" onclick="appendToDisplay('9')">9</button>
            <button class="btn operator" onclick="appendToDisplay('-')">-</button>
            
            <button class="btn" onclick="appendToDisplay('4')">4</button>
            <button class="btn" onclick="appendToDisplay('5')">5</button>
            <button class="btn" onclick="appendToDisplay('6')">6</button>
            <button class="btn operator" onclick="appendToDisplay('+')">+</button>
            
            <button class="btn" onclick="appendToDisplay('1')">1</button>
            <button class="btn" onclick="appendToDisplay('2')">2</button>
            <button class="btn" onclick="appendToDisplay('3')">3</button>
            <button class="btn operator" onclick="calculateResult()">=</button>
            
            <button class="btn zero" onclick="appendToDisplay('0')">0</button>
            <button class="btn" onclick="appendToDisplay('.')">.</button>
        </div>
        
        <div class="history" id="history">
            <div style="color: #ffffff; margin-bottom: 10px; font-size: 0.9rem;">
                <strong>History:</strong>
            </div>
        </div>
    </div>
    
    <script>
        let currentInput = '0';
        let history = [];
        
        function updateDisplay() {
            document.getElementById('display').textContent = currentInput;
        }
        
        function appendToDisplay(value) {
            if (currentInput === '0' && !isNaN(value)) {
                currentInput = value;
            } else {
                currentInput += value;
            }
            updateDisplay();
        }
        
        function clearDisplay() {
            currentInput = '0';
            updateDisplay();
        }
        
        function deleteLast() {
            if (currentInput.length > 1) {
                currentInput = currentInput.slice(0, -1);
            } else {
                currentInput = '0';
            }
            updateDisplay();
        }
        
        function calculateResult() {
            try {
                // Replace display symbols with JavaScript operators
                let expression = currentInput.replace(/×/g, '*').replace(/÷/g, '/');
                
                // Evaluate the expression
                let result = eval(expression);
                
                // Add to history
                addToHistory(currentInput + ' = ' + result);
                
                // Update display with result
                currentInput = result.toString();
                updateDisplay();
                
            } catch (error) {
                currentInput = 'Error';
                updateDisplay();
                setTimeout(() => {
                    currentInput = '0';
                    updateDisplay();
                }, 1500);
            }
        }
        
        function addToHistory(calculation) {
            history.unshift(calculation);
            if (history.length > 10) {
                history = history.slice(0, 10);
            }
            updateHistoryDisplay();
        }
        
        function updateHistoryDisplay() {
            const historyDiv = document.getElementById('history');
            const historyHTML = history.map(item => 
                `<div class="history-item">${item}</div>`
            ).join('');
            
            historyDiv.innerHTML = `
                <div style="color: #ffffff; margin-bottom: 10px; font-size: 0.9rem;">
                    <strong>History:</strong>
                </div>
                ${historyHTML}
            `;
        }
        
        // Keyboard support
        document.addEventListener('keydown', function(event) {
            const key = event.key;
            
            if (key >= '0' && key <= '9') {
                appendToDisplay(key);
            } else if (key === '.') {
                appendToDisplay('.');
            } else if (key === '+') {
                appendToDisplay('+');
            } else if (key === '-') {
                appendToDisplay('-');
            } else if (key === '*') {
                appendToDisplay('*');
            } else if (key === '/') {
                appendToDisplay('/');
            } else if (key === 'Enter' || key === '=') {
                calculateResult();
            } else if (key === 'Escape' || key === 'c' || key === 'C') {
                clearDisplay();
            } else if (key === 'Backspace') {
                deleteLast();
            }
            
            event.preventDefault();
        });
        
        // Initialize display
        updateDisplay();
    </script>
</body>
</html>
"""

@app.route('/')
def calculator():
    return render_template_string(CALCULATOR_TEMPLATE)

@app.route('/calculate', methods=['POST'])
def calculate():
    try:
        expression = request.form.get('expression', '')
        if not expression:
            return {'error': 'No expression provided'}
        
        # Basic security check
        if any(char in expression for char in [';', 'import', 'exec', 'eval']):
            return {'error': 'Invalid characters in expression'}
        
        # Evaluate the expression safely
        try:
            # Replace display symbols with actual operators
            expression = expression.replace('×', '*').replace('÷', '/')
            result = eval(expression)
            return {'result': str(result)}
        except:
            return {'error': 'Invalid expression'}
            
    except Exception as e:
        return {'error': str(e)}

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
