"""Test runtime detector with sample code"""
from runtime_detector import runtime_detector

# Test cases
test_cases = [
    ("Flask app", """
from flask import Flask
app = Flask(__name__)

@app.route('/')
def home():
    return 'Hello World'

if __name__ == '__main__':
    app.run()
"""),
    ("FastAPI app", """
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}
"""),
    ("Express.js", """
const express = require('express');
const app = express();

app.get('/', (req, res) => {
    res.send('Hello World');
});

app.listen(3000);
"""),
    ("React component", """
import React, { useState } from 'react';

function App() {
    const [count, setCount] = useState(0);
    return <div>Count: {count}</div>;
}
"""),
    ("Spring Boot", """
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
"""),
    ("Go web server", """
package main

import (
    "fmt"
    "net/http"
)

func main() {
    http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
        fmt.Fprintf(w, "Hello World")
    })
    http.ListenAndServe(":8080", nil)
}
"""),
    ("Rust program", """
fn main() {
    println!("Hello, world!");
}
"""),
    ("PHP script", """
<?php
echo "Hello World";
?>
"""),
    ("C program", """
#include <stdio.h>

int main() {
    printf("Hello World\\n");
    return 0;
}
"""),
    ("C++ program", """
#include <iostream>

int main() {
    std::cout << "Hello World" << std::endl;
    return 0;
}
"""),
    ("HTML page", """
<!DOCTYPE html>
<html>
<head>
    <title>Test</title>
</head>
<body>
    <h1>Hello World</h1>
</body>
</html>
"""),
]

print("🧪 Testing Runtime Detector\n")
print("=" * 60)

for name, code in test_cases:
    runtime_name, config = runtime_detector.detect(code)
    print(f"\n✅ {name}")
    print(f"   Runtime: {runtime_name}")
    print(f"   Image: {config['image']}")
    print(f"   Port: {config['port']}")
    print(f"   Filename: {config['filename']}")

print("\n" + "=" * 60)
print("✨ All tests completed!")
