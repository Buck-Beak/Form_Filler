# Playwright Form-Filler Bot - Architecture Diagrams

## System Architecture Diagram

```mermaid
graph TB
    subgraph "User Interface"
        A[Telegram User]
    end
    
    subgraph "Telegram Bot Layer"
        B[main.py<br/>Bot Orchestrator]
        B1[Command Handler<br/>/start]
        B2[Message Handler<br/>Form Request]
        B3[Callback Handler<br/>Button Click]
    end
    
    subgraph "Configuration Layer"
        C1[config.py<br/>Environment Variables]
        C2[forms.json<br/>Form Database]
        C3[users.json<br/>User Database]
        C4[.env<br/>Secrets]
    end
    
    subgraph "Browser Automation Layer"
        D[browser_utils.py<br/>Stealth Browser Setup]
        D1[Playwright Instance]
        D2[Chromium Browser]
        D3[Browser Context<br/>Anti-Detection]
        D4[Page Object]
    end
    
    subgraph "Form Processing Pipeline"
        E[form_extractor.py<br/>Field Extraction]
        E1[Main Frame Extraction]
        E2[IFrame Extraction]
        E3[Label Detection]
        E4[Visibility Filter]
        
        F[field_classifier.py<br/>AI Classification]
        F1[Gemini API]
        F2[Prompt Builder]
        F3[JSON Parser]
        
        G[form_filler.py<br/>Autofill Logic]
        G1[Key Mapper]
        G2[Selector Builder]
        G3[Frame Locator]
        G4[Type Simulator]
    end
    
    subgraph "External Services"
        H1[Google Gemini API<br/>AI Classification]
        H2[Telegram Bot API<br/>Messaging]
        H3[Target Website<br/>Forms]
    end
    
    A -->|1. Send Message| B
    B --> B1
    B --> B2
    B --> B3
    
    B2 -->|2. Lookup Form| C2
    B2 -->|3. Lookup User| C3
    B -->|Load Config| C1
    C1 -->|Load Secrets| C4
    
    B3 -->|4. Launch Browser| D
    D --> D1
    D1 --> D2
    D2 --> D3
    D3 --> D4
    
    D4 -->|5. Navigate| H3
    D4 -->|6. Extract Fields| E
    
    E --> E1
    E --> E2
    E --> E3
    E --> E4
    
    E -->|7. Fields Array| F
    F --> F2
    F2 -->|8. API Call| H1
    H1 -->|9. Classification| F3
    
    F -->|10. Classified Fields| G
    G --> G1
    G1 --> G2
    G2 --> G3
    G3 --> G4
    
    G4 -->|11. Fill Form| D4
    D4 -->|Update| H3
    
    B -->|12. Send Messages| H2
    H2 -->|Deliver| A
    
    style A fill:#e1f5ff
    style B fill:#fff4e1
    style D fill:#f0e1ff
    style E fill:#e1ffe1
    style F fill:#ffe1e1
    style G fill:#ffe1f5
    style H1 fill:#ffd7d7
    style H2 fill:#ffd7d7
    style H3 fill:#ffd7d7
```

## Component Interaction Flow

```mermaid
sequenceDiagram
    actor User
    participant TG as Telegram Bot<br/>(main.py)
    participant CFG as Config Layer<br/>(config, forms, users)
    participant BRW as Browser Utils<br/>(browser_utils.py)
    participant PW as Playwright<br/>Chromium
    participant EXT as Form Extractor<br/>(form_extractor.py)
    participant CLS as Field Classifier<br/>(field_classifier.py)
    participant GEM as Gemini API
    participant FIL as Form Filler<br/>(form_filler.py)
    participant WEB as Target Website
    
    User->>TG: /start command
    TG->>User: Welcome message
    
    User->>TG: "Fill JEE form"
    TG->>CFG: Lookup form URL
    CFG-->>TG: Return form URL
    TG->>CFG: Lookup user data
    CFG-->>TG: Return user profile
    TG->>User: Send "Open & Auto-Fill" button
    
    User->>TG: Click button
    TG->>User: "Opening browser..."
    
    TG->>BRW: launch_browser()
    BRW->>PW: Start Playwright
    BRW->>PW: Launch Chromium (stealth)
    BRW->>PW: Create context (fingerprint)
    BRW->>PW: Inject anti-detection scripts
    PW-->>BRW: Return page object
    BRW-->>TG: Return (playwright, browser, context, page)
    
    TG->>PW: page.goto(form_url)
    PW->>WEB: Navigate to form
    WEB-->>PW: Load page
    PW->>PW: Wait for DOM load + 5s
    
    TG->>EXT: extract_form_fields(page)
    EXT->>PW: Execute JS on main frame
    PW-->>EXT: Main frame fields
    EXT->>PW: Execute JS on all iframes
    PW-->>EXT: IFrame fields
    EXT-->>TG: Return all fields array
    
    TG->>CLS: classify_fields_with_gemini(fields)
    CLS->>GEM: Send classification prompt
    GEM-->>CLS: Return JSON classification
    CLS->>CLS: Parse & clean response
    CLS-->>TG: Return classified fields
    
    TG->>FIL: autofill_form(page, classified, user_data)
    loop For each field
        FIL->>FIL: Map category to user data
        FIL->>FIL: Build selector candidates
        FIL->>PW: Locate element in frame
        FIL->>PW: Click, clear, type value
        PW->>WEB: Update form field
    end
    FIL-->>TG: Return filled count
    
    TG->>User: "✅ Filled X fields"
    TG->>TG: Wait 5 minutes
    TG->>PW: Close browser
    PW->>PW: Cleanup
```

## Data Flow Architecture

```mermaid
flowchart LR
    subgraph INPUT["📥 Input Data"]
        A1[User Message]
        A2[forms.json]
        A3[users.json]
        A4[.env Secrets]
    end
    
    subgraph PROCESSING["⚙️ Processing Pipeline"]
        B1[URL Matching]
        B2[User Lookup]
        B3[Browser Launch]
        B4[Page Navigation]
        B5[Field Extraction]
        B6[AI Classification]
        B7[Data Mapping]
        B8[Autofill]
    end
    
    subgraph OUTPUT["📤 Output"]
        C1[Filled Form]
        C2[Success Message]
        C3[Diagnostic Logs]
    end
    
    A1 --> B1
    A2 --> B1
    A3 --> B2
    A4 --> B3
    
    B1 --> B3
    B2 --> B7
    B3 --> B4
    B4 --> B5
    B5 --> B6
    B6 --> B7
    B7 --> B8
    
    B8 --> C1
    B8 --> C2
    B5 --> C3
    B6 --> C3
    B8 --> C3
    
    style INPUT fill:#e1f5ff
    style PROCESSING fill:#fff4e1
    style OUTPUT fill:#e1ffe1
```

## Module Dependency Graph

```mermaid
graph TD
    A[main.py]
    B[config.py]
    C[browser_utils.py]
    D[form_extractor.py]
    E[field_classifier.py]
    F[form_filler.py]
    
    G[.env]
    H[forms.json]
    I[users.json]
    
    J[Playwright API]
    K[Telegram Bot API]
    L[Google Gemini API]
    
    A -->|imports| B
    A -->|imports| C
    A -->|imports| D
    A -->|imports| E
    A -->|imports| F
    
    B -->|reads| G
    A -->|reads| H
    A -->|reads| I
    
    C -->|uses| J
    D -->|uses| J
    F -->|uses| J
    
    A -->|uses| K
    E -->|uses| L
    
    style A fill:#ff9999
    style B fill:#99ccff
    style C fill:#99ccff
    style D fill:#99ccff
    style E fill:#99ccff
    style F fill:#99ccff
    style G fill:#ffcc99
    style H fill:#ffcc99
    style I fill:#ffcc99
    style J fill:#ccff99
    style K fill:#ccff99
    style L fill:#ccff99
```

## Stealth Browser Architecture

```mermaid
graph TB
    subgraph "Playwright Setup"
        A[async_playwright.start]
        B[Chromium Launch]
    end
    
    subgraph "Anti-Detection Layers"
        C1[Browser Args Layer]
        C2[Context Fingerprint Layer]
        C3[JavaScript Injection Layer]
    end
    
    subgraph "Browser Args"
        D1[--disable-blink-features=<br/>AutomationControlled]
        D2[--disable-dev-shm-usage]
        D3[--no-sandbox]
        D4[--disable-web-security]
        D5[--disable-features=<br/>IsolateOrigins]
    end
    
    subgraph "Context Fingerprint"
        E1[Viewport: 1920x1080]
        E2[User Agent: Chrome 131]
        E3[Locale: en-US]
        E4[Timezone: Asia/Kolkata]
        E5[HTTP Headers:<br/>Sec-Fetch-*, sec-ch-ua]
    end
    
    subgraph "JS Injection"
        F1[navigator.webdriver = undefined]
        F2["window.chrome = {runtime}"]
        F3["navigator.languages = en-US"]
        F4[navigator.platform = Win32]
    end
    
    subgraph "Result"
        G[Stealth Browser Page]
    end
    
    A --> B
    B --> C1
    C1 --> D1 & D2 & D3 & D4 & D5
    
    D1 & D2 & D3 & D4 & D5 --> C2
    C2 --> E1 & E2 & E3 & E4 & E5
    
    E1 & E2 & E3 & E4 & E5 --> C3
    C3 --> F1 & F2 & F3 & F4
    
    F1 & F2 & F3 & F4 --> G
    
    style A fill:#e1f5ff
    style B fill:#e1f5ff
    style C1 fill:#fff4e1
    style C2 fill:#fff4e1
    style C3 fill:#fff4e1
    style G fill:#e1ffe1
```

## Field Extraction Pipeline

```mermaid
flowchart TD
    A[Start Extraction] --> B[Define JS Extraction Code]
    
    B --> C{Extract Main Frame}
    C -->|Success| D[Mark fields: frame=main]
    C -->|Error| E[Log warning, continue]
    
    D --> F[Add to all_fields list]
    E --> F
    
    F --> G{For each iframe}
    G -->|More frames| H{Execute JS in frame}
    G -->|No more| M[Return all_fields]
    
    H -->|Success| I[Mark fields: frame=url/name]
    H -->|Error| J[Log warning, skip frame]
    
    I --> K[Add to all_fields list]
    J --> L[Continue to next frame]
    K --> L
    L --> G
    
    subgraph "JS Extraction Logic"
        N[Query all visible inputs/<br/>textarea/select]
        O[Extract: id, name, placeholder,<br/>type, formcontrolname, aria-label]
        P["Find label text:<br/>1. label for=id<br/>2. Parent container label<br/>3. aria-label/placeholder"]
        Q[Check visibility:<br/>getBoundingClientRect]
        R[Build field object]
    end
    
    B -.-> N
    N --> O
    O --> P
    P --> Q
    Q --> R
    
    style A fill:#e1f5ff
    style M fill:#e1ffe1
    style N fill:#fff4e1
    style O fill:#fff4e1
    style P fill:#fff4e1
    style Q fill:#fff4e1
    style R fill:#fff4e1
```

## Autofill Decision Tree

```mermaid
flowchart TD
    A[Start Autofill] --> B{For each classified field}
    
    B -->|Next field| C[Extract field metadata:<br/>id, name, category, frame]
    B -->|Done| Z[Return filled_count]
    
    C --> D{Map category to user data}
    D -->|Found mapping| E[Get value from user_data]
    D -->|No mapping| F[Use category as key]
    
    E --> G{Value exists?}
    F --> G
    
    G -->|Yes| H["Build selector candidates:<br/>1. ID selector<br/>2. Name attribute<br/>3. Formcontrolname<br/>4. Placeholder<br/>5. Aria-label"]
    G -->|No| I[Log: Skip - no value]
    
    I --> B
    
    H --> J{Locate target frame}
    J -->|Main frame| K[Use page.main_frame]
    J -->|IFrame| L[Search frames by url/name]
    
    K --> M{Try each selector}
    L --> M
    
    M -->|Next selector| N{Element exists?}
    M -->|All failed| O[Log: Could not fill]
    
    N -->|No| M
    N -->|Yes| P{Element visible?}
    
    P -->|No| M
    P -->|Yes| Q[Click element]
    
    Q --> R[Wait 0.1s]
    R --> S[Clear field]
    S --> T[Wait 0.1s]
    T --> U[Type value<br/>delay=50ms/char]
    
    U --> V[Increment filled_count]
    V --> W[Log: Success]
    W --> B
    O --> B
    
    style A fill:#e1f5ff
    style Z fill:#e1ffe1
    style W fill:#ccffcc
    style I fill:#ffcccc
    style O fill:#ffcccc
```

## Error Handling Flow

```mermaid
flowchart TD
    A[User Request] --> B{Form exists in DB?}
    B -->|No| C[❌ Form not found]
    B -->|Yes| D{User exists in DB?}
    
    D -->|No| E[❌ User not found]
    D -->|Yes| F[Launch Browser]
    
    F --> G{Browser launched?}
    G -->|No| H[❌ Browser error]
    G -->|Yes| I[Navigate to URL]
    
    I --> J{Page loaded?}
    J -->|Timeout| K[❌ Page load timeout]
    J -->|Yes| L[Extract Fields]
    
    L --> M{Fields found?}
    M -->|No fields| N[Retry 10x with 1s delay]
    M -->|Yes| O[Classify with Gemini]
    
    N --> P{Retry succeeded?}
    P -->|No| Q[⚠️ No fields detected]
    P -->|Yes| O
    
    O --> R{Classification valid?}
    R -->|Parse error| S[⚠️ Empty classification]
    R -->|Success| T[Autofill Form]
    
    S --> T
    Q --> T
    
    T --> U{Autofill succeeded?}
    U -->|Partial| V[✅ Filled X fields<br/>⚠️ Some failed]
    U -->|All filled| W[✅ All fields filled]
    U -->|None| X[❌ Autofill failed]
    
    C --> Y[Send error to user]
    E --> Y
    H --> Y
    K --> Y
    V --> Z[Send success to user]
    W --> Z
    X --> Y
    
    Y --> AA[Cleanup & Exit]
    Z --> AB[Wait 5min → Close browser]
    AB --> AA
    
    style C fill:#ffcccc
    style E fill:#ffcccc
    style H fill:#ffcccc
    style K fill:#ffcccc
    style Q fill:#ffffcc
    style S fill:#ffffcc
    style V fill:#ffffcc
    style X fill:#ffcccc
    style W fill:#ccffcc
    style Z fill:#ccffcc
```

## Deployment Architecture

```mermaid
graph TB
    subgraph "Development Environment"
        A[Local Machine]
        B[VS Code]
        C[Python 3.10+]
        D[Git Repository]
    end
    
    subgraph "Runtime Dependencies"
        E[Playwright<br/>Browser Drivers]
        F[Chromium Binary]
        G[Python Packages<br/>requirements.txt]
    end
    
    subgraph "Configuration Files"
        H[.env<br/>Secrets]
        I[forms.json<br/>Form Database]
        J[users.json<br/>User Database]
    end
    
    subgraph "External APIs"
        K[Telegram Bot API<br/>cloud-based]
        L[Google Gemini API<br/>cloud-based]
    end
    
    subgraph "Target Systems"
        M[Government Websites]
        N[Educational Portals]
        O[Tax Portals]
    end
    
    A --> B
    B --> C
    C --> D
    
    C --> E
    E --> F
    C --> G
    
    C --> H
    C --> I
    C --> J
    
    C --> K
    C --> L
    
    F --> M
    F --> N
    F --> O
    
    style A fill:#e1f5ff
    style K fill:#ffe1e1
    style L fill:#ffe1e1
    style M fill:#fff4e1
    style N fill:#fff4e1
    style O fill:#fff4e1
```

---

## How to View These Diagrams

### Option 1: GitHub/GitLab
- Push this file to your repository
- View on GitHub/GitLab (they render Mermaid natively)

### Option 2: VS Code Extension
- Install "Markdown Preview Mermaid Support" extension
- Open this file and click "Preview" (Ctrl+Shift+V)

### Option 3: Online Viewer
- Copy any diagram code
- Paste at: https://mermaid.live/

### Option 4: Mermaid CLI
```bash
npm install -g @mermaid-js/mermaid-cli
mmdc -i ARCHITECTURE_DIAGRAM.md -o architecture.pdf
```

---

## Diagram Descriptions

1. **System Architecture**: Complete system overview with all components and data flow
2. **Component Interaction Flow**: Detailed sequence diagram showing step-by-step execution
3. **Data Flow Architecture**: High-level data transformation pipeline
4. **Module Dependency Graph**: Shows which modules depend on which
5. **Stealth Browser Architecture**: How anti-detection is implemented
6. **Field Extraction Pipeline**: Detailed field extraction logic
7. **Autofill Decision Tree**: Logic flow for filling each field
8. **Error Handling Flow**: Complete error scenarios and recovery
9. **Deployment Architecture**: Development and runtime environment setup
