package com.acme.comptes;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/accounts")
public class AccountsController {
    @GetMapping("/{id}")
    public String detail(@PathVariable("id") Long id) {
        return "ok";
    }

    @GetMapping
    public String list() {
        return "ok";
    }
}
