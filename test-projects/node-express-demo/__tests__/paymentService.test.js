const { calculateTotal } = require('../src/paymentService');

describe('paymentService', () => {
  test('calculateTotal returns sum of item prices', () => {
    const items = [{ price: 10 }, { price: 20 }, { price: 5 }];
    expect(calculateTotal(items)).toBe(35);
  });

  // NOTE: chargeCustomer and refundPayment are NOT tested.
  // The agent will detect uncovered lines and create tests for them.
});
