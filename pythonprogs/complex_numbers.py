import math

class ComplexNumber(object):
    """ Represents complex numbers and lets you
    to do operations on it.
    """
    def __init__(self, real=0.00, imaginary=0.00):
        self.r = real
        self.i = imaginary
        self.complex_num = self.__get_me_complex_number(real, imaginary)

        def __get_me_complex_number(self, r, i):
            if i < 0:
                return "%0.2f-%0.2fi" % (r, abs(i))
            else:
                return "%0.2f+%0.2fi" % (r, abs(i))

        def __str__(self):
                return self.complex_num

        def __add__(self, other_complex_num):
            i = self.i + other_complex_num.i
            r = self.r + other_complex_num.r
            return ComplexNumber(r, i)

        def __sub__(self, other_complex_num):
            i = self.i - other_complex_num.i
            r = self.r - other_complex_num.r
            return ComplexNumber(r, i)

        def __mul__(self, other_complex_num):
                r = (self.r * other_complex_num.r - self.i * other_complex_num.i)
                i = self.i * other_complex_num.r + self.r * other_complex_num.i
                return ComplexNumber(r, i)

        def __div__(self, other_complex_num):
                mult = other_complex_num.conjugate()
                divident = float(mult.i ** 2  + mult.r ** 2)
                multiplier = self * mult
                r = multiplier.r / divident
                i = multiplier.i / divident
                return ComplexNumber(r, i)

        def conjugate(self):
                return ComplexNumber(self.r, -self.i)

        def mod(self):
                r = math.sqrt(self.r ** 2 + self.i ** 2)
                return ComplexNumber(r)

#first_comp = raw_input().strip().split(" ")
#sec_comp = raw_input().strip().split(" ")

#x1,y1 = float(first_comp[0]), float(first_comp[1])
#x2, y2 = float(sec_comp[0]), float(sec_comp[1])

x1, y1 =  1.2, 3
x2, y2 = 2.2, 5
a = ComplexNumber(x1, y1)
b = ComplexNumber(x2, y2)
print a+b
print a-b
print a*b
print a/b
print a.mod()
print b.mod()
