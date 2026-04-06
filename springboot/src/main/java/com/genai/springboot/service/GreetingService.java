package com.genai.springboot.service;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String getGreeting() {
        return "Spring Boot API is running";
    }
}
