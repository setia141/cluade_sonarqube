package com.demo;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.web.client.RestTemplate;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    RestTemplate restTemplate;

    @InjectMocks
    OrderService orderService;

    @Test
    void checkInventory_returnsTrue_whenStockSufficient() {
        when(restTemplate.getForObject(anyString(), eq(Map.class)))
            .thenReturn(Map.of("available", 10));

        assertThat(orderService.checkInventory("prod-1", 5)).isTrue();
    }

    // NOTE: processOrder and getOrderHistory are NOT tested here.
    // The agent will detect uncovered lines and create tests for them.
}
