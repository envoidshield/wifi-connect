// Prevent multiple executions of this script
if (!window.KioskBoardInitialized) {
    window.KioskBoardInitialized = true;
    
    // Global flag to ensure single initialization
    window.KioskBoardPasswordInitialized = false;
    
    // Initialize KioskBoard configuration (only once)
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
        language: 'en',
        theme: 'dark',
        autoScroll: true,
        capsLockActive: false,
        keysSpecialCharsArrayOfStrings: [
            '!', '@', '#', '$', '%', '^', '&', '*', '(', ')',
            '-', '_', '=', '+', '[', ']', '{', '}', '|', '\\',
            ':', ';', '"', '\'', '<', '>', ',', '.', '?', '/',
            '`', '~', '€', '£', '¥', '©', '®', '™', '°', '±'
        ],
        keysNumpadArrayOfNumbers: [1, 2, 3, 4, 5, 6, 7, 8, 9, 0],
    });
    
    // Expose function to initialize keyboard on modal
    window.initKeyboardForModal = function() {
        // Absolute single initialization check
        if (window.KioskBoardPasswordInitialized) {
            console.log('KioskBoard already initialized (global check)');
            return;
        }
        
        // Find the password input using class selector
        const input = document.querySelector('.connect-password');
        if (!input) {
            console.log('Password input not found');
            return;
        }
        
        // Set the global flag BEFORE calling KioskBoard.run
        // This prevents ANY possibility of double initialization
        window.KioskBoardPasswordInitialized = true;
        
        // Run KioskBoard on this input ONLY ONCE using class selector
        console.log('Initializing KioskBoard on password input (ONCE)');
        KioskBoard.run('.connect-password');
    };
    
    // Removed automatic initialization to prevent any interference
    // All initialization now happens explicitly through initKeyboardForModal()
}