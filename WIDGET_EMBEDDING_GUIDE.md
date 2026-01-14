# AI Receptionist - Widget Embedding Guide

   This guide explains how to embed the AI Receptionist chat widget into your Wix website.

   ---

   ## Widget URLs

   | Widget | URL |
   |--------|-----|
   | **Consulate** | http://ai-receptionist-widget.s3-website.us-east-2.amazonaws.com/consulate-widget.html |
   | **Real Estate** | http://ai-receptionist-widget.s3-website.us-east-2.amazonaws.com/realestate-widget.html |
   | **Both (selector)** | http://ai-receptionist-widget.s3-website.us-east-2.amazonaws.com/chat-widget.html |

   ---

   ## Option 1: Embed in Wix Using HTML iFrame

   ### Steps:

   1. Open your Wix website editor

   2. Click **Add Elements** (+ icon) in the left sidebar

   3. Select **Embed Code** → **Embed HTML**

   4. Drag the HTML element to where you want the chat widget

   5. Click on the element and select **Enter Code**

   6. Paste this code for **Consulate**:
```
   <iframe 
       src="http://ai-receptionist-widget.s3-website.us-east-2.amazonaws.com/consulate-widget.html"
       width="400"
       height="550"
       frameborder="0"
       style="border: none; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.15);">
   </iframe>
```

   7. Or paste this code for **Real Estate**:
```
   <iframe 
       src="http://ai-receptionist-widget.s3-website.us-east-2.amazonaws.com/realestate-widget.html"
       width="400"
       height="550"
       frameborder="0"
       style="border: none; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.15);">
   </iframe>
```

   8. Click **Update** and then **Publish** your site

   ---

   ## Option 2: Floating Chat Button (Advanced)

   For a floating chat button that opens the widget, paste this entire code block:
```
   <style>
       .chat-button {
           position: fixed;
           bottom: 20px;
           right: 20px;
           width: 60px;
           height: 60px;
           border-radius: 50%;
           background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
           border: none;
           cursor: pointer;
           box-shadow: 0 4px 20px rgba(0,0,0,0.3);
           z-index: 9998;
           display: flex;
           align-items: center;
           justify-content: center;
           font-size: 28px;
           transition: transform 0.3s;
       }
       .chat-button:hover {
           transform: scale(1.1);
       }
       .chat-popup {
           position: fixed;
           bottom: 90px;
           right: 20px;
           width: 400px;
           height: 550px;
           border: none;
           border-radius: 16px;
           box-shadow: 0 10px 40px rgba(0,0,0,0.3);
           z-index: 9999;
           display: none;
       }
       .chat-popup.open {
           display: block;
       }
   </style>

   <button class="chat-button" onclick="toggleChat()">💬</button>

   <iframe 
       id="chat-popup"
       class="chat-popup"
       src="http://ai-receptionist-widget.s3-website.us-east-2.amazonaws.com/consulate-widget.html">
   </iframe>

   <script>
       function toggleChat() {
           const popup = document.getElementById('chat-popup');
           popup.classList.toggle('open');
       }
   </script>
```

   ---

   ## Customization

   ### Adjust Size
   Change the width and height values in the iframe code:
   - **Desktop:** width="400" height="550"
   - **Mobile:** width="100%" height="500"

   ### Different Pages
   - Use the **Consulate widget** on consulate-related pages
   - Use the **Real Estate widget** on property-related pages

   ---

   ## Demo Links (Share These!)

   - **Consulate Demo:** http://ai-receptionist-widget.s3-website.us-east-2.amazonaws.com/consulate-widget.html
   - **Real Estate Demo:** http://ai-receptionist-widget.s3-website.us-east-2.amazonaws.com/realestate-widget.html

   ---

   ## Support

   For technical support or customization requests, contact: [Your Contact Info]