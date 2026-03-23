import React from "react";
import { ExternalLink, Github, Twitter } from "lucide-react";

export default function Footer() {
  return (
    <footer className="footer">
      <div className="footer__divider"></div>
      <div className="footer__content">
        <div className="footer__brand">
          <img
            src="https://github.com/data-umbrella.png"
            alt="Data Umbrella Logo"
            className="footer__logo"
          />
          <span className="footer__company-name">Data Umbrella</span>
          <div className="footer__socials">
            <a
              href="https://github.com/data-umbrella"
              aria-label="GitHub"
              className="footer__social-link"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Github size={20} strokeWidth={1.5} />
            </a>
            <a
              href="https://twitter.com/dataumbrella"
              aria-label="Twitter"
              className="footer__social-link"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Twitter size={20} strokeWidth={1.5} />
            </a>
          </div>
        </div>

        <div className="footer__links">
          <div className="footer__column">
            <a
              href="https://www.dataumbrella.org/about/about-data-umbrella"
              target="_blank"
              rel="noopener noreferrer"
            >
              About Us{" "}
              <ExternalLink size={14} className="footer__external-icon" />
            </a>
            <a
              href="https://www.dataumbrella.org/about/faq"
              target="_blank"
              rel="noopener noreferrer"
            >
              FAQs <ExternalLink size={14} className="footer__external-icon" />
            </a>
          </div>

          <div className="footer__column">
            <a
              href="https://www.every.org/data-umbrella"
              target="_blank"
              rel="noopener noreferrer"
            >
              Donate{" "}
              <ExternalLink size={14} className="footer__external-icon" />
            </a>
            <a
              href="https://www.dataumbrella.org/about/sponsors"
              target="_blank"
              rel="noopener noreferrer"
            >
              Sponsors{" "}
              <ExternalLink size={14} className="footer__external-icon" />
            </a>
          </div>

          <div className="footer__column">
            <a
              href="https://www.dataumbrella.org/about/contact"
              target="_blank"
              rel="noopener noreferrer"
            >
              Contact Us{" "}
              <ExternalLink size={14} className="footer__external-icon" />
            </a>
            <a
              href="https://www.dataumbrella.org/"
              target="_blank"
              rel="noopener noreferrer"
            >
              Data Umbrella{" "}
              <ExternalLink size={14} className="footer__external-icon" />
            </a>
          </div>
        </div>
      </div>
      <div className="footer__copyright">
        &copy; Data Umbrella {new Date().getFullYear()}
      </div>
    </footer>
  );
}
