package com.genai.springboot.controller;

import com.genai.springboot.dto.ApiResponse;
import com.genai.springboot.service.GreetingService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/health")
public class HealthController {

    private final GreetingService greetingService;

    public HealthController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping
    public ApiResponse<String> health() {
        return ApiResponse.success("Service is healthy", greetingService.getGreeting());
    }
}
