package com.acme.service;

import com.acme.domain.Client;
import org.springframework.stereotype.Service;

@Service
public class ClientService {
    private final Client repository;

    public ClientService(Client repository) {
        this.repository = repository;
    }

    public Client find(Long id) {
        return repository;
    }
}
