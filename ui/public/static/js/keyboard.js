KioskBoard.init({
    keysArrayOfObjects: [
     {
        "0": "Q",
        "1": "W",
        "2": "E",
        "3": "R",
        "4": "T",
        "5": "Y",
        "6": "U",
        "7": "I",
        "8": "O",
        "9": "P"
     },
     {
        "0": "A",
        "1": "S",
        "2": "D",
        "3": "F",
        "4": "G",
        "5": "H",
        "6": "J",
        "7": "K",
        "8": "L"
     },
     {
        "0": "Z",
        "1": "X",
        "2": "C",
        "3": "V",
        "4": "B",
        "5": "N",
        "6": "M"
     }
  ],
        // Language Code (ISO 639-1) for custom keys (for language support) => e.g. "de" || "en" || "fr" || "hu" || "tr" etc...
    language: 'en',
  
    // The theme of keyboard => "light" || "dark" || "flat" || "material" || "oldschool"
    theme: 'dark',
  
    // Scrolls the document to the top or bottom(by the placement option) of the input/textarea element. Prevented when "false"
    autoScroll: true,
  
    // Uppercase or lowercase to start. Uppercased when "true"
    capsLockActive: false,
  
    keysSpecialCharsArrayOfStrings: [
      '!', '@', '#', '$', '%', '^', '&', '*', '(', ')',
      '-', '_', '=', '+', '[', ']', '{', '}', '|', '\\',
      ':', ';', '"', '\'', '<', '>', ',', '.', '?', '/',
      '`', '~', '€', '£', '¥', '©', '®', '™', '°', '±'
    ],
    keysNumpadArrayOfNumbers: [1, 2, 3, 4, 5, 6, 7, 8, 9, 0],
  });
  KioskBoard.run('.js-kioskboard-input')