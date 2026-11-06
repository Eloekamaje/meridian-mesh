package com.acme.antifraude;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.*;

@FeignClient(name = "comptes-api", url = "${comptes.base-url}", path = "/accounts")
public interface ComptesClient {
    @GetMapping("/{id}")
    String get(@PathVariable("id") Long id);
}
