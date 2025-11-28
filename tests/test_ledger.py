import pytest
from src.ledger import CreditLedger

def test_new_user_bonus():
    """Проверка: Новый юзер должен получить бонус."""
    # Используем базу в памяти (исчезнет после теста)
    ledger = CreditLedger(":memory:")
    
    wallet = "WalletA"
    balance = ledger.get_or_create_user(wallet, welcome_bonus=2.0)
    
    assert balance == 2.0
    print("\n✅ New user bonus credited correctly")

def test_deduction_logic():
    """Проверка: Списание средств работает корректно."""
    ledger = CreditLedger(":memory:")
    wallet = "WalletB"
    
    # 1. Создаем юзера с $2.00
    ledger.get_or_create_user(wallet, welcome_bonus=2.0)
    
    # 2. Пытаемся списать $0.05
    success = ledger.attempt_deduction(wallet, cost=0.05, welcome_bonus=2.0)
    assert success == True
    
    # 3. Проверяем остаток ($2.00 - $0.05 = $1.95)
    new_balance = ledger.get_or_create_user(wallet, 2.0)
    assert new_balance == 1.95
    print("\n✅ Balance deducted correctly")

def test_insufficient_funds():
    """Проверка: Если денег нет, списание не проходит."""
    ledger = CreditLedger(":memory:")
    wallet = "PoorWallet"
    
    # Даем бонус $0.00 (для теста)
    ledger.get_or_create_user(wallet, welcome_bonus=0.0)
    
    success = ledger.attempt_deduction(wallet, cost=0.05, welcome_bonus=0.0)
    assert success == False
    print("\n✅ Insufficient funds blocked correctly")