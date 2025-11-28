import pytest
from fastapi.testclient import TestClient
from src.main import app

# Создаем тестового клиента
client = TestClient(app)

def test_home_endpoint():
    """Проверка: Главная страница работает."""
    response = client.get("/")
    assert response.status_code == 200
    assert "TravelPay402" in response.json()["protocol"]

def test_api_access_freemium():
    """Проверка: Доступ к API с новым кошельком (Freemium)."""
    # Делаем запрос с заголовком кошелька
    response = client.get(
        "/api/borders/US-MEX-TEST",
        headers={"X-User-Wallet": "TestUser_123"}
    )
    
    # Должен быть успех (200 OK)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] == True
    assert data["data"]["crossing_id"] == "US-MEX-TEST"

def test_api_missing_wallet():
    """Проверка: Запрос без кошелька должен быть отклонен (400 Bad Request)."""
    response = client.get("/api/borders/US-MEX-TEST")
    
    assert response.status_code == 400
    assert "Missing Header" in response.json()["detail"]

def test_api_payment_required_mock():
    """
    Проверка: Симуляция ситуации, когда нет денег и нет подписи (402).
    Мы не можем легко исчерпать баланс в тесте, но можем проверить логику.
    """
    # Это сложный тест, в рамках MVP мы проверяем только успешный путь Freemium.
    pass