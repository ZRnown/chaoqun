# ui/styles.py

def get_stylesheet():
    return """
    QMainWindow {
        background-color: #f5f5f7; /* Mac-like light gray */
    }

    /* Sidebar Styling */
    QWidget#Sidebar {
        background-color: #2c3e50;
        border-right: 1px solid #dcdcdc;
    }

    QLabel#AppTitle {
        color: white;
        font-size: 18px;
        font-weight: bold;
        padding: 20px 10px;
    }

    QPushButton.SidebarBtn {
        background-color: transparent;
        color: #ecf0f1;
        text-align: left;
        padding: 12px 20px;
        border: none;
        font-size: 14px;
        border-radius: 5px;
        margin: 2px 10px;
    }

    QPushButton.SidebarBtn:hover {
        background-color: #34495e;
    }

    QPushButton.SidebarBtn:checked {
        background-color: #3498db;
        color: white;
        font-weight: bold;
    }



    /* Buttons */
    QPushButton {
        background-color: #ffffff;
        border: 1px solid #d0d0d0;
        border-radius: 6px;
        padding: 6px 15px;
        color: #333;
        min-width: 80px;
    }

    QPushButton:hover {
        background-color: #f0f0f0;
    }

    QPushButton.PrimaryBtn {
        background-color: #007AFF; /* Mac Blue */
        color: white;
        border: none;
    }

    QPushButton.PrimaryBtn:hover {
        background-color: #0069d9;
    }

    QPushButton.SuccessBtn {
        background-color: #28a745;
        color: white;
        border: none;
    }

    QPushButton.SuccessBtn:hover {
        background-color: #218838;
    }

    /* Inputs and Lists */
    QLineEdit, QTextEdit, QListWidget {
        border: 1px solid #e0e0e0;
        border-radius: 6px;
        padding: 5px;
        background-color: white;
        selection-background-color: #007AFF;
    }

    QListWidget::item {
        padding: 8px;
        border-bottom: 1px solid #f0f0f0;
    }

    QListWidget::item:selected {
        background-color: #e3f2fd;
        color: #1976d2;
    }

    /* Labels */
    QLabel {
        color: #333;
    }

    QLabel.Subtitle {
        color: #666;
        font-size: 12px;
    }

    /* Progress Bar */
    QProgressBar {
        border: 1px solid #e0e0e0;
        border-radius: 3px;
        text-align: center;
    }

    QProgressBar::chunk {
        background-color: #007AFF;
    }


    """
