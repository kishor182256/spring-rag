package com.genai.springboot.service;

import com.genai.springboot.dto.FastApiStatusResponse;
import com.genai.springboot.dto.FastApiUploadResponse;
import com.genai.springboot.exception.FileStorageException;
import com.genai.springboot.exception.ResourceNotFoundException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.util.UriComponentsBuilder;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;
import java.nio.file.Path;
import java.util.Map;

@Service
public class FastApiIngestService {

    private final String fastApiIngestUrl;
    private final String fastApiProcessUrlTemplate;
    private final String fastApiStatusUrlTemplate;
    private final String fastApiChunksUrlTemplate;
    private final RestTemplate restTemplate;

    public FastApiIngestService(
            @Value("${app.fastapi.ingest-url}") String fastApiIngestUrl,
            @Value("${app.fastapi.process-url-template}") String fastApiProcessUrlTemplate,
            @Value("${app.fastapi.status-url-template}") String fastApiStatusUrlTemplate,
            @Value("${app.fastapi.chunks-url-template}") String fastApiChunksUrlTemplate
    ) {
        this.fastApiIngestUrl = fastApiIngestUrl;
        this.fastApiProcessUrlTemplate = fastApiProcessUrlTemplate;
        this.fastApiStatusUrlTemplate = fastApiStatusUrlTemplate;
        this.fastApiChunksUrlTemplate = fastApiChunksUrlTemplate;
        this.restTemplate = new RestTemplate();
    }

    public void uploadToIngest(Path localFilePath, String fileId) {
        try {
            FileSystemResource fileResource = new FileSystemResource(localFilePath);
            MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
            body.add("file", fileResource);
            body.add("file_id", fileId);

            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.MULTIPART_FORM_DATA);

            HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, headers);

            ResponseEntity<FastApiUploadResponse> response =
                    restTemplate.postForEntity(fastApiIngestUrl, requestEntity, FastApiUploadResponse.class);

            FastApiUploadResponse responseBody = response.getBody();
            if (responseBody == null) {
                throw new FileStorageException("FastAPI upload response is empty");
            }

            if (!responseBody.success() || responseBody.data() == null) {
                throw new FileStorageException("FastAPI upload failed: " + responseBody.message());
            }
        } catch (RestClientException ex) {
            throw new FileStorageException("Failed to call FastAPI ingest endpoint", ex);
        }
    }

    public void triggerProcessing(String fileId) {
        String processUrl = fastApiProcessUrlTemplate.replace("{fileId}", fileId);
        try {
            ResponseEntity<FastApiStatusResponse> response =
                    restTemplate.postForEntity(processUrl, HttpEntity.EMPTY, FastApiStatusResponse.class);

            FastApiStatusResponse responseBody = response.getBody();
            if (responseBody == null || !responseBody.success() || responseBody.data() == null) {
                throw new FileStorageException("Failed to trigger FastAPI processing");
            }
        } catch (HttpClientErrorException.NotFound ex) {
            throw new ResourceNotFoundException("File id not found in FastAPI: " + fileId);
        } catch (RestClientException ex) {
            throw new FileStorageException("Failed to trigger FastAPI processing", ex);
        }
    }

    public String fetchProcessingStatus(String fileId) {
        String statusUrl = fastApiStatusUrlTemplate.replace("{fileId}", fileId);
        try {
            ResponseEntity<FastApiStatusResponse> response =
                    restTemplate.getForEntity(statusUrl, FastApiStatusResponse.class);

            FastApiStatusResponse responseBody = response.getBody();
            if (responseBody == null || !responseBody.success() || responseBody.data() == null) {
                throw new FileStorageException("Failed to fetch FastAPI processing status");
            }
            return responseBody.data().status();
        } catch (HttpClientErrorException.NotFound ex) {
            throw new ResourceNotFoundException("File id not found: " + fileId);
        } catch (RestClientException ex) {
            throw new FileStorageException("Failed to fetch FastAPI processing status", ex);
        }
    }

    @SuppressWarnings("unchecked")
    public Object fetchChunks(String fileId, int offset, int limit, boolean includeText) {
        String chunksUrlTemplate = fastApiChunksUrlTemplate.replace("{fileId}", fileId);
        String chunksUrl = UriComponentsBuilder
                .fromUriString(chunksUrlTemplate)
                .queryParam("offset", offset)
                .queryParam("limit", limit)
                .queryParam("include_text", includeText)
                .build()
                .toUriString();
        try {
            ResponseEntity<Map> response = restTemplate.getForEntity(chunksUrl, Map.class);
            Map<String, Object> responseBody = response.getBody();
            if (responseBody == null) {
                throw new FileStorageException("Failed to fetch chunks: empty response");
            }

            Object successValue = responseBody.get("success");
            Object data = responseBody.get("data");
            if (!(successValue instanceof Boolean success) || !success || data == null) {
                throw new FileStorageException("Failed to fetch chunks from FastAPI");
            }
            return data;
        } catch (HttpClientErrorException.NotFound ex) {
            throw new ResourceNotFoundException("File id not found: " + fileId);
        } catch (RestClientException ex) {
            throw new FileStorageException("Failed to fetch chunks from FastAPI", ex);
        }
    }
}
