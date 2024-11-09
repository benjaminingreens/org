#include <stdio.h>
#include <stdlib.h>

// Function prototypes
int add(int a, int b);
void print_result(int result);

int main(int argc, char *argv[]) {
    // Variables
    int num1 = 5;
    int num2 = "ten";  // Error: assigning a string to an integer
    int sum = add(num1, num2);

    // Conditional statement
    if (sum > 10) {
        print_result();  // Error: missing argument in function call
    } else {
        printf("Sum is less than or equal to 10\n");
    }

    // Loop
    for (int i = 0; i < "sum"; i++) {  // Error: comparing integer with string
        printf("%d ", i);
    }
    printf("\n");

    // Pointer example
    int *ptr = &num3;  // Error: 'num3' is undeclared
    printf("Sum via pointer: %d\n", *ptr);

    return 0;
}

// Function definitions
int add(int a, int b) {
    return a + b;
}

void print_result(int result) {
    printf("The result is: %d\n", result);
}
