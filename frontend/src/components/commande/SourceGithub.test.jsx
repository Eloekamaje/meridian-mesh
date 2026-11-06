import { act } from "react";
import { createRoot } from "react-dom/client";
import api from "@/lib/api";
import SourceGithub from "./SourceGithub";

jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));
jest.mock("@/components/ui/popover", () => ({
  Popover: ({ children }) => <div>{children}</div>,
  PopoverTrigger: ({ children }) => children,
  PopoverContent: ({ children }) => <div>{children}</div>,
}));
jest.mock("@/components/ui/command", () => ({
  Command: ({ children }) => <div>{children}</div>,
  CommandEmpty: ({ children }) => <div>{children}</div>,
  CommandInput: () => null,
  CommandItem: ({ children }) => <div>{children}</div>,
  CommandList: ({ children }) => <div>{children}</div>,
}));

global.IS_REACT_ACT_ENVIRONMENT = true;

beforeEach(() => {
  jest.clearAllMocks();
  api.get.mockResolvedValue({
    data: [{ id: "gh-x", nom: "Compte X", login: "x", avatar: "" }],
  });
});

test("permet de redéclarer le jeton du compte sélectionné", async () => {
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  await act(async () => {
    racine.render(<SourceGithub source={{ id: "s1", config: { connexion: "gh-x" } }} onChange={jest.fn()} />);
  });
  await act(async () => { await Promise.resolve(); });

  const bouton = hote.querySelector('[data-testid="insp-github-redeclarer"]');
  expect(bouton.textContent).toContain("@x");
  await act(async () => { bouton.click(); });
  expect(hote.querySelector('[data-testid="insp-github-jeton"]')).not.toBeNull();

  await act(async () => { racine.unmount(); });
});
