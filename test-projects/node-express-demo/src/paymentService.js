const axios = require('axios');

const PAYMENT_URL = process.env.PAYMENT_SERVICE_URL || 'http://localhost:8081';

// javascript:S2814 — 'total' re-declared using var
function calculateTotal(items) {
  var total = 0;
  for (const item of items) {
    var total = total + item.price; // S2814: re-declares 'total' in same scope
  }
  return total;
}

// javascript:S1481 — unused variable 'requestId'
async function chargeCustomer(customerId, amount) {
  const requestId = `req_${Date.now()}`; // S1481: never used after assignment
  const response = await axios.post(`${PAYMENT_URL}/charge`, {
    customerId,
    amount,
  });
  return response.data;
}

// javascript:S3827 — 'logger' is not defined
async function refundPayment(paymentId) {
  const response = await axios.post(`${PAYMENT_URL}/refund`, { paymentId });
  logger.info(`Refund processed: ${paymentId}`); // S3827: logger is not defined
  return response.data;
}

module.exports = { calculateTotal, chargeCustomer, refundPayment };
