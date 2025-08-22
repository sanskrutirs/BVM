# math1.py
'''x = 10
y = 3
z = 2'''


'''if x < 5:
    y = 5
else:
    y = 6'''


'''sum = 0
for i in range(9):
    sum = sum + i'''

'''x = 10
while x > 0:
    x = x - 1
    if x == 9:
        break'''


'''# Simple operations
a = x + y
b = x - y

# Nested operations
c = (x + y) % z
d = (x * y) - (z + 5)

# Comparisons with expressions
e = (x + y) < (z * 5)'''

# contracts/inefficient_sum.py
'''sum = 0
i = 1
while i <= 10:
    if i > 0:  # Unnecessary check
        temp = sum + i
        sum = temp
    i += 1'''

# contracts/efficient_sum.py
sum = 0
sum = 1 + 2 + 3 + 4 + 5 + 6 + 7 + 8 + 9 + 10  # Direct calculation

sum=55
'''a=5
b=6
sum=a+b'''
