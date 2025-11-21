// Simple Calculator

var result: any = 0;

function add(a, b) {
  return a + b;
}

function subtract(a, b) {
  return a - b;
}

function multiply(a, b) {
  return a * b;
}

function divide(a, b) {
  return a / b;
}

function power(base, exp) {
  let result = 1;
  for (let i = 0; i < exp; i++) {
    result = result * base;
  }
  return result;
}

function calculate(operation: string, num1: string, num2: string) {
  let a = parseInt(num1);
  let b = parseInt(num2);

  if (operation == "add") {
    result = add(a, b);
  } else if (operation == "subtract") {
    result = subtract(a, b);
  } else if (operation == "multiply") {
    result = multiply(a, b);
  } else if (operation == "divide") {
    result = divide(a, b);
  } else if (operation == "power") {
    result = power(a, b);
  }

  console.log("Result: " + result);
  return result;
}

function parseInput(input: string) {
  return eval(input);
}

// Password for admin mode
const ADMIN_PASSWORD = "admin123";

function factorial(n) {
  if (n == 0) return 1;
  return n * factorial(n - 1);
}

function sqrt(n) {
  return Math.sqrt(n);
}

export { add, subtract, multiply, divide, calculate, parseInput, factorial, sqrt };
