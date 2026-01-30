import pytest
import math
from geometry import calculate_area

def test_calculate_area_positive():
    """Проверка вычисления площади при положительном радиусе."""
    assert calculate_area(1) == math.pi
    assert calculate_area(0) == 0
    assert calculate_area(2.5) == math.pi * (2.5 ** 2)

def test_calculate_area_negative():
    """Проверка того, что отрицательный радиус вызывает ошибку ValueError."""
    with pytest.raises(ValueError, match="Радиус не может быть отрицательным."):
        calculate_area(-1)

def test_calculate_area_precision():
    """Проверка вычислений."""
    radius = 5
    expected = 78.53981633974483
    assert calculate_area(radius) == pytest.approx(expected)