import math

def calculate_area(radius: float) -> float:
    """
    Вычисляет площадь круга по его радиусу.
    param radius - радиус круга.
    return - площадь круга.
    raises ValueError - если радиус меньше нуля.
    """
    if radius < 0:
        raise ValueError("Радиус не может быть отрицательным.")
    
    return math.pi * (radius ** 2)