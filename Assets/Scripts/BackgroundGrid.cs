using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class BackgroundGrid : MonoBehaviour
{
    public GameObject horizontalLine;
    public GameObject verticalLine;
    public int gridWidth = 50;
    public int gridHeight = 50;
    public float gridSpacing = 1;
    public float xOffset = -0.5f;
    public float yOffset = -0.5f;

    // Start is called before the first frame update
    void Start()
    {
        for (int i = 0; i <= gridWidth; i++)
        {
            GameObject line = Instantiate(horizontalLine, transform);
            line.GetComponent<LineRenderer>().SetPosition(0, new Vector3(i * gridSpacing + xOffset, yOffset, 0));
            line.GetComponent<LineRenderer>().SetPosition(1, new Vector3(i * gridSpacing + xOffset, gridWidth + yOffset, 0));
            if (i%5 == 0)
            {
                line.GetComponent<LineRenderer>().startWidth = 0.05f;
                line.GetComponent<LineRenderer>().endWidth = 0.05f;
            }
        }

        for (int i = 0; i <= gridHeight; i++)
        {
            GameObject line = Instantiate(verticalLine, transform);
            line.GetComponent<LineRenderer>().SetPosition(0, new Vector3(xOffset, i * gridSpacing + yOffset, 0));
            line.GetComponent<LineRenderer>().SetPosition(1, new Vector3(gridHeight + xOffset, i * gridSpacing + yOffset, 0));
            if (i % 5 == 0)
            {
                line.GetComponent<LineRenderer>().startWidth = 0.05f;
                line.GetComponent<LineRenderer>().endWidth = 0.05f;
            }
        }
    }
}
