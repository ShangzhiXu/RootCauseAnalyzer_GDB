#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_TRANSACTIONS 10
#define NAME_LENGTH 5

typedef enum {
    DEPOSIT,
    WITHDRAWAL
} TransactionType;

typedef struct {
    TransactionType type;
    double amount;
    char description[10];
} Transaction;

typedef struct {
    int accountNumber;
    char holderName[NAME_LENGTH];
    double balance;
    Transaction transactions[MAX_TRANSACTIONS];
    int transactionCount;
} BankAccount;

BankAccount* createAccount(int accountNumber, const char* holderName);
int deposit(BankAccount* account, double amount, const char* description);
int withdraw(BankAccount* account, double amount, const char* description);
void printAccountDetails(const BankAccount* account);
void printTransactionHistory(const BankAccount* account);
BankAccount* findAccount(BankAccount** accounts, int totalAccounts, int accountNumber);
void transfer(BankAccount** accounts, int totalAccounts, int fromAccNum, int toAccNum, double amount);
void simulateOperations();

void addTransaction(BankAccount* account, TransactionType type, double amount, const char* description);

int main() {
    simulateOperations();
    return 0;
}

BankAccount* createAccount(int accountNumber, const char* holderName) {
    BankAccount* newAccount = (BankAccount*)malloc(sizeof(BankAccount));
    if (!newAccount) {
        return NULL;
    }
    newAccount->accountNumber = accountNumber;
    strncpy(newAccount->holderName, holderName, NAME_LENGTH);
    newAccount->balance = 0.0;
    newAccount->transactionCount = 0;
    return newAccount;
}

void addTransaction(BankAccount* account, TransactionType type, double amount, const char* description) {
    if (account->transactionCount >= MAX_TRANSACTIONS) {
        return;
    }
    Transaction* txn = &account->transactions[account->transactionCount++];
    txn->type = type;
    txn->amount = amount;
    strncpy(txn->description, description, 10);
}

int deposit(BankAccount* account, double amount, const char* description) {
    if (amount <= 0) {
        return -1;
    }
    account->balance += amount;
    addTransaction(account, DEPOSIT, amount, description);
    return 0;
}

int withdraw(BankAccount* account, double amount, const char* description) {
    if (amount <= 0) {
        return -1;
    }
    if (account->balance < amount) {
        return -1;
    }
    account->balance -= amount;
    addTransaction(account, WITHDRAWAL, amount, description);
    return 0;
}

void printAccountDetails(const BankAccount* account) {
}

void printTransactionHistory(const BankAccount* account) {
}

BankAccount* findAccount(BankAccount** accounts, int totalAccounts, int accountNumber) {
    for (int i = 0; i < totalAccounts; i++) {
        if (accounts[i]->accountNumber == accountNumber) {
            return accounts[i];
        }
    }
    return NULL;
}

void transfer(BankAccount** accounts, int totalAccounts, int fromAccNum, int toAccNum, double amount) {
    BankAccount* fromAccount = findAccount(accounts, totalAccounts, fromAccNum);
    BankAccount* toAccount = findAccount(accounts, totalAccounts, toAccNum);
    if (!fromAccount || !toAccount) {
        return;
    }
    if (withdraw(fromAccount, amount, "Transfer to") == 0) {
        deposit(toAccount, amount, "Transfer from");
    }
}

void simulateOperations() {
    int totalAccounts = 3;
    BankAccount* accounts[3];

    accounts[0] = createAccount(1001, "Alice");
    accounts[1] = createAccount(1002, "Bob");
    accounts[2] = createAccount(1003, "Charlie");

    deposit(accounts[0], 500.0, "Initial");
    deposit(accounts[1], 1000.0, "Initial");
    deposit(accounts[2], 750.0, "Initial");

    withdraw(accounts[1], 200.0, "withdrawal");
    withdraw(accounts[2], 50.0, "shopping");

    transfer(accounts, totalAccounts, 1001, 1003, 150.0);

    for (int i = 0; i < totalAccounts; i++) {
        printAccountDetails(accounts[i]);
        printTransactionHistory(accounts[i]);
    }

    for (int i = 0; i < totalAccounts; i++) {
        free(accounts[i]);
    }
}

