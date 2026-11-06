package com.acme.antifraude;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/internal/accounts")
public class InternalAccountsController {
    @GetMapping("/{id}")
    public String detail(@PathVariable("id") Long id) {
        return "ok";
    }
}
