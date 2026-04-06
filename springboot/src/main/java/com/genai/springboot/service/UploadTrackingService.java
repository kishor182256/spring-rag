package com.genai.springboot.service;

import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class UploadTrackingService {

    private final Map<String, String> statusByFileId = new ConcurrentHashMap<>();
    private final Map<String, String> failureReasonByFileId = new ConcurrentHashMap<>();

    public void setStatus(String fileId, String status) {
        statusByFileId.put(fileId, status);
        if (!"FAILED".equals(status)) {
            failureReasonByFileId.remove(fileId);
        }
    }

    public String getStatus(String fileId) {
        return statusByFileId.get(fileId);
    }

    public boolean exists(String fileId) {
        return statusByFileId.containsKey(fileId);
    }

    public void setFailure(String fileId, String reason) {
        statusByFileId.put(fileId, "FAILED");
        failureReasonByFileId.put(fileId, reason);
    }

    public String getFailureReason(String fileId) {
        return failureReasonByFileId.get(fileId);
    }
}
