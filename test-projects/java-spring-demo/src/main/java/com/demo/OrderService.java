package com.demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.List;
import java.util.Map;

@Service
public class OrderService {

    private final RestTemplate restTemplate;

    @Value("${payment.service.url}")
    private String paymentUrl;

    @Value("${inventory.service.url}")
    private String inventoryUrl;

    public OrderService(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    // SonarQube S2259 — null dereference
    // getForObject can return null but result is used without null check
    public String processOrder(String orderId, double amount) {
        Map response = restTemplate.getForObject(
            paymentUrl + "/charge?amount=" + amount, Map.class
        );
        return response.get("transactionId").toString(); // NPE if response or transactionId is null
    }

    // SonarQube S1481 — unused local variable
    public boolean checkInventory(String productId, int quantity) {
        String unusedDebugInfo = "checking product " + productId; // never used
        Map result = restTemplate.getForObject(
            inventoryUrl + "/stock/" + productId, Map.class
        );
        if (result == null) {
            return false;
        }
        return (int) result.get("available") >= quantity;
    }

    // SonarQube S1166 — exception swallowed without logging or rethrowing
    public List<Map> getOrderHistory(String customerId) {
        try {
            Map response = restTemplate.getForObject(
                paymentUrl + "/history/" + customerId, Map.class
            );
            return (List<Map>) response.get("orders");
        } catch (Exception e) {
            // exception swallowed — S1166
            return List.of();
        }
    }
}
