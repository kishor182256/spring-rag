package com.genai.aiadapter.service;

import com.genai.aiadapter.exception.ProxyException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.util.UriComponentsBuilder;

import java.io.IOException;
import java.util.Map;

@Service
public class FastApiProxyService {

    private final RestTemplate restTemplate;
    private final String fastApiBaseUrl;

    public FastApiProxyService(
            RestTemplate restTemplate,
            @Value("${app.fastapi.base-url}") String fastApiBaseUrl
    ) {
        this.restTemplate = restTemplate;
        this.fastApiBaseUrl = fastApiBaseUrl;
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> forwardChatQuery(Map<String, Object> payload) {
        String url = fastApiBaseUrl + "/api/v1/chat/query";
        try {
            ResponseEntity<Map> response = restTemplate.postForEntity(url, payload, Map.class);
            if (response.getBody() == null) {
                throw new ProxyException("FastAPI chat response is empty");
            }
            return response.getBody();
        } catch (RestClientException ex) {
            throw new ProxyException("Failed to call FastAPI chat endpoint", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> forwardIngestUpload(MultipartFile file, String fileId) {
        String url = fastApiBaseUrl + "/api/v1/ingest/upload";

        try {
            ByteArrayResource resource = new ByteArrayResource(file.getBytes()) {
                @Override
                public String getFilename() {
                    return file.getOriginalFilename();
                }
            };

            MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
            body.add("file", resource);
            if (fileId != null && !fileId.isBlank()) {
                body.add("file_id", fileId);
            }

            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.MULTIPART_FORM_DATA);
            HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, headers);

            ResponseEntity<Map> response = restTemplate.postForEntity(url, requestEntity, Map.class);
            if (response.getBody() == null) {
                throw new ProxyException("FastAPI ingest upload response is empty");
            }
            return response.getBody();
        } catch (IOException ex) {
            throw new ProxyException("Failed to read upload file", ex);
        } catch (RestClientException ex) {
            throw new ProxyException("Failed to call FastAPI ingest upload endpoint", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> forwardIngestProcess(String fileId) {
        String url = fastApiBaseUrl + "/api/v1/ingest/" + fileId + "/process";
        try {
            ResponseEntity<Map> response = restTemplate.postForEntity(url, HttpEntity.EMPTY, Map.class);
            if (response.getBody() == null) {
                throw new ProxyException("FastAPI ingest process response is empty");
            }
            return response.getBody();
        } catch (RestClientException ex) {
            throw new ProxyException("Failed to call FastAPI ingest process endpoint", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> forwardIngestStatus(String fileId) {
        String url = fastApiBaseUrl + "/api/v1/ingest/" + fileId + "/status";
        try {
            ResponseEntity<Map> response = restTemplate.getForEntity(url, Map.class);
            if (response.getBody() == null) {
                throw new ProxyException("FastAPI ingest status response is empty");
            }
            return response.getBody();
        } catch (RestClientException ex) {
            throw new ProxyException("Failed to call FastAPI ingest status endpoint", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> forwardIngestChunks(String fileId, int offset, int limit, boolean includeText) {
        String url = UriComponentsBuilder
                .fromHttpUrl(fastApiBaseUrl + "/api/v1/ingest/" + fileId + "/chunks")
                .queryParam("offset", offset)
                .queryParam("limit", limit)
                .queryParam("include_text", includeText)
                .toUriString();
        try {
            ResponseEntity<Map> response = restTemplate.getForEntity(url, Map.class);
            if (response.getBody() == null) {
                throw new ProxyException("FastAPI ingest chunks response is empty");
            }
            return response.getBody();
        } catch (RestClientException ex) {
            throw new ProxyException("Failed to call FastAPI ingest chunks endpoint", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> forwardHealth() {
        String url = fastApiBaseUrl + "/api/v1/health";
        try {
            ResponseEntity<Map> response = restTemplate.exchange(url, HttpMethod.GET, HttpEntity.EMPTY, Map.class);
            if (response.getBody() == null) {
                throw new ProxyException("FastAPI health response is empty");
            }
            return response.getBody();
        } catch (RestClientException ex) {
            throw new ProxyException("Failed to call FastAPI health endpoint", ex);
        }
    }
}